// 全局采集缓存：单例 SSE 连接，多页面共享，供首页卡片/顶栏告警使用
import { create } from 'zustand'
import { getToken } from '../api/client'
import type { CollectData } from '../api/types'

let es: EventSource | null = null
let esToken = ''

interface CacheState {
  data: Record<string, CollectData>
  connect: () => void
  disconnect: () => void
}

export const useCacheStore = create<CacheState>((set) => ({
  data: {},
  connect: () => {
    const token = getToken()
    if (!token) return
    // token 变化（换号/重新登录）时先断开旧连接再重建
    if (es && esToken !== token) {
      es.close()
      es = null
    }
    if (es) return
    esToken = token
    es = new EventSource(`/api/stream?token=${encodeURIComponent(token)}`)
    let firstMessage = true
    es.onmessage = (ev) => {
      try {
        const updates = JSON.parse(ev.data) as Record<string, CollectData>
        // 首次消息为后端全量快照：整体替换（清除已删除服务器的残留数据）；之后增量合并
        set((s) => (firstMessage ? { data: updates } : { data: { ...s.data, ...updates } }))
        firstMessage = false
      } catch {
        // 心跳等非 JSON 消息忽略
      }
    }
    es.onerror = () => {
      // EventSource 自动重连
    }
  },
  disconnect: () => {
    es?.close()
    es = null
    esToken = ''
  },
}))

// 从缓存数据中计算告警服务器：任一查询/检查出现 error
export function collectAlerts(data: Record<string, CollectData>): { id: string; name: string; error: string }[] {
  const alerts: { id: string; name: string; error: string }[] = []
  for (const [id, d] of Object.entries(data)) {
    let firstErr = ''
    if (d.os_info) {
      for (const key of Object.keys(d.os_info)) {
        if (d.os_info[key]?.error) {
          firstErr = `${firstErr}${key}:${d.os_info[key].error} `
        }
      }
    }
    if (!firstErr && d.db_queries) {
      for (const cat of Object.keys(d.db_queries)) {
        for (const q of Object.keys(d.db_queries[cat])) {
          const qr = d.db_queries[cat][q]
          if (qr?.error) {
            firstErr = qr.error
            break
          }
        }
        if (firstErr) break
      }
    }
    if (firstErr) {
      alerts.push({ id, name: d.server || id, error: firstErr.slice(0, 200) })
    }
  }
  return alerts
}
