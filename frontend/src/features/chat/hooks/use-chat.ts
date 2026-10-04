import { useState, useCallback, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  createSession,
  listSessions,
  getSessionMessages,
  deleteSession,
  streamChat,
  cancelChatGeneration,
} from '@/api/chat'
import { QUERY_KEYS } from '@/lib/constants'

// 会话列表
export function useChatSessions(meetingId?: string) {
  return useQuery({
    queryKey: QUERY_KEYS.chatSessions(meetingId || ''),
    queryFn: () => listSessions(meetingId),
  })
}

// 会话消息
export function useSessionMessages(sessionId: string | null) {
  return useQuery({
    queryKey: QUERY_KEYS.chatMessages(sessionId || ''),
    queryFn: () => getSessionMessages(sessionId!),
    enabled: !!sessionId,
  })
}

// 创建会话
export function useCreateSession() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: createSession,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['chat-sessions'] })
    },
  })
}

// 删除会话
export function useDeleteSession() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: deleteSession,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['chat-sessions'] })
    },
  })
}

// 流式对话
interface StreamOptions {
  generationId: string
  images?: string[]
  onDone?: (content: string) => void
  onError?: (message: string, content: string) => void
  onStopped?: (content: string) => void
}

export function useStreamChat() {
  const queryClient = useQueryClient()
  const [isStreaming, setIsStreaming] = useState(false)
  const [streamingContent, setStreamingContent] = useState('')
  const [isReconnecting, setIsReconnecting] = useState(false)
  const active = useRef<{
    id: string
    sessionId: string
    controller: AbortController
    content: string
    frameId: number | null
    onStopped?: (content: string) => void
  } | null>(null)

  const cancelCurrent = useCallback(() => {
    const previous = active.current
    active.current = null
    if (previous) {
      if (previous.frameId !== null) {
        cancelAnimationFrame(previous.frameId)
        previous.frameId = null
      }
      previous.controller.abort()
      void cancelChatGeneration(previous.sessionId, previous.id).catch((error) => {
        // 离线时取消请求可能无法送达；后端的断开等待上限会回收无人订阅的任务。
        console.error('发送取消请求失败:', error)
      })
    }
    return previous
  }, [])

  const reset = useCallback(() => {
    cancelCurrent()
    setStreamingContent('')
    setIsStreaming(false)
    setIsReconnecting(false)
  }, [cancelCurrent])

  useEffect(
    () => () => {
      cancelCurrent()
    },
    [cancelCurrent],
  )

  const stop = useCallback(() => {
    const current = cancelCurrent()
    if (!current) return
    current.onStopped?.(current.content)
    setIsStreaming(false)
    setStreamingContent('')
    setIsReconnecting(false)
  }, [cancelCurrent])

  const stream = useCallback(
    async (sessionId: string, query: string, options: StreamOptions) => {
      reset()
      const current: NonNullable<typeof active.current> = {
        id: options.generationId,
        sessionId,
        controller: new AbortController(),
        content: '',
        frameId: null,
        onStopped: options.onStopped,
      }
      active.current = current
      setIsStreaming(true)
      setStreamingContent('')

      try {
        let terminalEvent: 'done' | 'error' | 'cancelled' | undefined
        let streamError = ''

        await streamChat(
          sessionId,
          query,
          options.images,
          (event) => {
            // abort 前已经排队的旧回调，也不能写入新一轮生成。
            if (active.current !== current || event.generation_id !== current.id) return
            if (event.type === 'token' && event.content) {
              // 接收时立即保存完整内容；一帧内到达的增量只提交一次 React 更新。
              current.content += event.content
              if (current.frameId === null) {
                current.frameId = requestAnimationFrame(() => {
                  current.frameId = null
                  if (active.current === current && !current.controller.signal.aborted) {
                    setStreamingContent(current.content)
                  }
                })
              }
            } else if (event.type === 'done') {
              terminalEvent = 'done'
            } else if (event.type === 'error') {
              terminalEvent = 'error'
              streamError = event.message || '未知错误'
            } else if (event.type === 'cancelled') {
              terminalEvent = 'cancelled'
            }
          },
          current.controller.signal,
          current.id,
          (reconnecting) => {
            if (active.current === current) setIsReconnecting(reconnecting)
          },
        )

        // fetch-event-source 收到 abort 后会 resolve，不会自动抛 AbortError。
        if (active.current !== current || current.controller.signal.aborted) return

        // 使用接收缓冲收尾，不依赖最后一帧是否已经绘制（后台页面也不会丢尾字）。
        if (terminalEvent === 'done') {
          options.onDone?.(current.content)
        } else if (terminalEvent === 'error') {
          options.onError?.(streamError, current.content)
        } else if (terminalEvent === 'cancelled') {
          options.onStopped?.(current.content)
        } else {
          throw new Error('流式响应意外结束')
        }
      } catch (err) {
        if (active.current === current && !current.controller.signal.aborted) {
          options.onError?.(err instanceof Error ? err.message : '请求失败', current.content)
        }
      } finally {
        if (active.current === current) {
          if (current.frameId !== null) {
            cancelAnimationFrame(current.frameId)
            current.frameId = null
          }
          active.current = null
          setIsStreaming(false)
          setStreamingContent('')
          setIsReconnecting(false)
        }
        void queryClient.invalidateQueries({
          queryKey: QUERY_KEYS.chatMessages(sessionId),
        })
      }
    },
    [queryClient, reset],
  )

  return { stream, isStreaming, streamingContent, isReconnecting, stop, reset }
}
