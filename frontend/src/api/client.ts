/** 统一请求封装：拼后端地址、抛网络错误、给页脚留一句可读的说明。 */
const API_BASE = import.meta.env.VITE_API_BASE ?? ''

export function request(path: string, init?: RequestInit): Promise<Response> {
  const url = path.startsWith('http') ? path : `${API_BASE}${path}`
  return fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  }).catch((error: unknown) => {
    const detail = error instanceof Error ? error.message : '请求未送达'
    throw new Error(`接口请求失败：${detail}`)
  })
}

export async function fetchJson<T>(path: string): Promise<T> {
  const response = await request(path)
  if (!response.ok) {
    throw new Error(`接口返回 ${response.status}，数据未更新`)
  }
  return (await response.json()) as T
}

export interface ActionPayload {
  ok?: boolean
  message?: string
  detail?: string
  entry?: Record<string, unknown>
}

function reasonFrom(data: unknown): string | undefined {
  if (data && typeof data === 'object') {
    const detail = (data as Record<string, unknown>).detail
    if (typeof detail === 'string' && detail.trim()) return detail
    if (Array.isArray(detail) && detail.length) {
      const first = detail[0] as Record<string, unknown>
      if (typeof first?.msg === 'string' && first.msg.trim()) return first.msg
    }
    const message = (data as Record<string, unknown>).message
    if (typeof message === 'string' && message.trim()) return message
  }
  return undefined
}

/** 从错误响应里挑出后端给出的可读原因（detail 或 message），没有就用兜底文案。 */
export async function extractError(response: Response, fallback: string): Promise<string> {
  try {
    return reasonFrom(await response.json()) ?? `${fallback}（HTTP ${response.status}）`
  } catch {
    /* 响应体不是 JSON 时走兜底文案 */
    return `${fallback}（HTTP ${response.status}）`
  }
}

/** 动作类接口统一收口：HTTP 非 2xx 或 ok=false 都视为失败，并带上后端给出的原因。 */
export async function parseAction(response: Response, fallback: string): Promise<ActionPayload> {
  const payload = (await response.json().catch(() => null)) as ActionPayload | null
  if (!response.ok) {
    throw new Error(reasonFrom(payload) ?? `${fallback}（HTTP ${response.status}）`)
  }
  if (payload && payload.ok === false) {
    throw new Error(payload.message && payload.message.trim() ? payload.message : fallback)
  }
  return payload ?? {}
}
