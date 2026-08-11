// SSE 实时订阅：复用全局缓存 store（单例连接）
import { useEffect } from 'react'
import { getToken } from '../api/client'
import { useCacheStore } from '../store/cache'
import type { CollectData } from '../api/types'

export function useServerCache(): Record<string, CollectData> {
  const data = useCacheStore((s) => s.data)
  useEffect(() => {
    useCacheStore.getState().connect()
  }, [])
  return data
}

// 手动拉取单台服务器缓存（用于详情页等场景）
export async function fetchServerData(serverId: string): Promise<CollectData | null> {
  const resp = await fetch(`/api/servers/${serverId}/data`, {
    headers: getToken() ? { Authorization: `Bearer ${getToken()}` } : {},
  })
  if (!resp.ok) return null
  return resp.json()
}
