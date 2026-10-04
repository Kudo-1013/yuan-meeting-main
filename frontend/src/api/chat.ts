import { apiClient } from './client'
import { streamJsonEvents, StreamHttpError } from './sse'
import type { ChatSession, ChatMessage, ChatSSEEvent } from '@/types'

// 创建会话
export async function createSession(data: {
  meeting_id?: string
  title?: string
}): Promise<ChatSession> {
  return apiClient.post('chat/sessions', { json: data }).json()
}

// 获取会话列表
export async function listSessions(meetingId?: string): Promise<ChatSession[]> {
  return apiClient
    .get('chat/sessions', {
      searchParams: meetingId ? { meeting_id: meetingId } : {},
    })
    .json()
}

// 获取会话消息
export async function getSessionMessages(sessionId: string): Promise<ChatMessage[]> {
  return apiClient.get(`chat/sessions/${sessionId}/messages`).json()
}

// 删除会话
export async function deleteSession(sessionId: string): Promise<void> {
  await apiClient.delete(`chat/sessions/${sessionId}`)
}

// SSE 流式对话
export async function streamChat(
  sessionId: string,
  query: string,
  images?: string[],
  onEvent?: (event: ChatSSEEvent) => void,
  signal?: AbortSignal,
  generationId: string = crypto.randomUUID(),
  onConnectionChange?: (reconnecting: boolean) => void,
): Promise<void> {
  let lastSeq = 0
  let resume = false
  let failures = 0

  while (!signal?.aborted) {
    let terminal = false
    const connection = new AbortController()
    const disconnect = () => connection.abort()
    signal?.addEventListener('abort', disconnect, { once: true })
    window.addEventListener('offline', disconnect)
    if (signal?.aborted || !navigator.onLine) disconnect()
    try {
      await streamJsonEvents<ChatSSEEvent>(
        `chat/sessions/${sessionId}/stream`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            query,
            images,
            generation_id: generationId,
            last_seq: lastSeq,
            resume,
          }),
          signal: connection.signal,
        },
        (event) => {
          if (event.generation_id !== generationId || event.seq <= lastSeq) return
          if (!Number.isSafeInteger(event.seq) || event.seq !== lastSeq + 1) {
            throw new Error('事件序号不连续，需要恢复遗漏内容')
          }
          onEvent?.(event)
          lastSeq = event.seq
          failures = 0
          terminal = event.type !== 'token'
        },
        () => onConnectionChange?.(false),
      )
      if (signal?.aborted || terminal) return
      throw new Error('流式连接提前结束')
    } catch (error) {
      if (signal?.aborted || terminal) return
      if (
        error instanceof StreamHttpError &&
        error.status >= 400 &&
        error.status < 500 &&
        error.status !== 429
      ) {
        throw error
      }
      if (++failures > 10) {
        throw new Error('连接恢复失败，已保留收到的文字，请稍后重新加载会话')
      }
      resume = true
      onConnectionChange?.(true)
      // abort 同时结束退避等待，点击停止后不会偷偷再次建立连接。
      await new Promise<void>((resolve) => {
        const finish = () => {
          clearTimeout(timer)
          signal?.removeEventListener('abort', finish)
          resolve()
        }
        const timer = setTimeout(finish, Math.min(500 * 2 ** (failures - 1), 4000))
        if (signal?.aborted) finish()
        else signal?.addEventListener('abort', finish, { once: true })
      })
    } finally {
      signal?.removeEventListener('abort', disconnect)
      window.removeEventListener('offline', disconnect)
    }
  }
}

export async function cancelChatGeneration(sessionId: string, generationId: string): Promise<void> {
  await apiClient.post(`chat/sessions/${sessionId}/generations/${generationId}/cancel`, {
    keepalive: true,
    timeout: 5000,
    retry: { limit: 2, methods: ['post'] },
  })
}
