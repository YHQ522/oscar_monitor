// 认证状态：token + 当前用户
import { create } from 'zustand'
import { api, clearToken, getToken, setToken } from '../api/client'
import { useCacheStore } from './cache'
import type { User } from '../api/types'

interface AuthState {
  user: User | null
  token: string | null
  ready: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => void
  fetchUser: () => Promise<void>
}

export const useAuth = create<AuthState>((set) => ({
  user: null,
  token: getToken(),
  ready: false,

  login: async (username, password) => {
    const data = await api.post<{ token: string; user: User }>('/api/auth/login', { username, password })
    setToken(data.token)
    set({ token: data.token, user: data.user, ready: true })
  },

  logout: () => {
    clearToken()
    // 断开 SSE 连接，避免旧 token 连接残留并阻塞新账号连接
    useCacheStore.getState().disconnect()
    set({ user: null, token: null, ready: true })
  },

  fetchUser: async () => {
    try {
      const user = await api.get<User>('/api/auth/me')
      set({ user, ready: true })
    } catch {
      clearToken()
      set({ user: null, token: null, ready: true })
    }
  },
}))
