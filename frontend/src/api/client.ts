// API 客户端：fetch 封装，自动携带 JWT，统一错误处理

const TOKEN_KEY = 'oscar_token'

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY)
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  }
  const token = getToken()
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const resp = await fetch(path, { ...options, headers })
  if (resp.status === 401) {
    clearToken()
    if (!path.includes('/auth/login')) {
      window.location.href = '/login'
    }
    throw new ApiError(401, '未登录或会话已过期')
  }

  const contentType = resp.headers.get('content-type') || ''
  if (contentType.includes('application/json')) {
    const data = await resp.json()
    if (!resp.ok) {
      const detail = (data as { detail?: string }).detail
      throw new ApiError(resp.status, detail || '请求失败')
    }
    return data as T
  }
  if (!resp.ok) {
    throw new ApiError(resp.status, `请求失败 (${resp.status})`)
  }
  return (await resp.text()) as unknown as T
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'PUT', body: body ? JSON.stringify(body) : undefined }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
}

// 下载文件（带 token 的 GET 下载）
export async function downloadFile(path: string, fallbackName: string): Promise<void> {
  const token = getToken()
  const resp = await fetch(path, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
  if (!resp.ok) {
    throw new ApiError(resp.status, `下载失败 (${resp.status})`)
  }
  const blob = await resp.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  const disposition = resp.headers.get('content-disposition') || ''
  const match = disposition.match(/filename="?([^";]+)"?/)
  a.download = match ? match[1] : fallbackName
  a.click()
  URL.revokeObjectURL(url)
}
