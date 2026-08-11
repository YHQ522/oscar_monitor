// 告警静默状态 — 本地持久化：静默的服务器不再计入顶栏告警（可随时恢复）
import { create } from 'zustand'

const KEY = 'oscar_muted_alerts'

interface AlertSettingsState {
  muted: Record<string, string> // serverId -> name（存名字便于展示与恢复）
  toggleMute: (id: string, name: string) => void
  unmute: (id: string) => void
}

function loadMuted(): Record<string, string> {
  try {
    return JSON.parse(localStorage.getItem(KEY) || '{}')
  } catch {
    return {}
  }
}

function saveMuted(muted: Record<string, string>) {
  try {
    localStorage.setItem(KEY, JSON.stringify(muted))
  } catch {
    /* ignore */
  }
}

export const useAlertSettings = create<AlertSettingsState>((set, get) => ({
  muted: loadMuted(),
  toggleMute: (id, name) => {
    const next = { ...get().muted }
    if (next[id]) delete next[id]
    else next[id] = name
    saveMuted(next)
    set({ muted: next })
  },
  unmute: (id) => {
    const next = { ...get().muted }
    delete next[id]
    saveMuted(next)
    set({ muted: next })
  },
}))
