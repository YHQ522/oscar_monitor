// 主题模式状态：light / dark，持久化到 localStorage
import { create } from 'zustand'

type Mode = 'light' | 'dark'

interface ThemeState {
  mode: Mode
  toggle: () => void
  setMode: (mode: Mode) => void
}

const KEY = 'oscar_theme'

function initialMode(): Mode {
  try {
    return (localStorage.getItem(KEY) as Mode) || 'light'
  } catch {
    return 'light'
  }
}

function applyBody(mode: Mode) {
  try {
    document.body.style.background = mode === 'dark' ? '#0f1117' : '#f5f6fa'
  } catch {
    /* ignore */
  }
}

const initial = initialMode()
// 初始化时同步 body 背景（刷新/重进后保持深色）
applyBody(initial)

export const useThemeStore = create<ThemeState>((set, get) => ({
  mode: initial,
  toggle: () => get().setMode(get().mode === 'light' ? 'dark' : 'light'),
  setMode: (mode) => {
    try {
      localStorage.setItem(KEY, mode)
    } catch {
      /* ignore */
    }
    applyBody(mode)
    set({ mode })
  },
}))
