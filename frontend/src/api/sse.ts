import { EventStreamContentType, fetchEventSource } from '@microsoft/fetch-event-source'
import { API_BASE_URL } from '@/lib/constants'

interface StreamRequest {
  method?: string
  headers?: Record<string, string>
  body?: string
  signal?: AbortSignal
}

export class StreamHttpError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export async function streamJsonEvents<T>(
  path: string,
  request: StreamRequest,
  onEvent: (event: T) => void,
  onOpen?: () => void,
): Promise<void> {
  // fetch-event-source 的 abort 会正常结束 Promise；已取消的请求不要再建流。
  if (request.signal?.aborted) return
  await fetchEventSource(`${API_BASE_URL}/${path}`, {
    ...request,
    openWhenHidden: true,
    headers: {
      Accept: EventStreamContentType,
      ...request.headers,
    },
    async onopen(response) {
      const contentType = response.headers.get('content-type')
      if (!response.ok) {
        const body = await response.json().catch(() => null)
        throw new StreamHttpError(
          response.status,
          typeof body?.detail === 'string' ? body.detail : `请求失败: ${response.status}`,
        )
      }
      if (!contentType?.startsWith(EventStreamContentType)) {
        throw new Error(`响应不是 SSE: ${contentType || 'unknown'}`)
      }
      onOpen?.()
    },
    onmessage(message) {
      if (!request.signal?.aborted && message.data) {
        onEvent(JSON.parse(message.data) as T)
      }
    },
    onerror(error) {
      // 通用层不自动重发 POST；聊天层会携带生成 ID 和游标显式恢复。
      throw error
    },
  })
}
