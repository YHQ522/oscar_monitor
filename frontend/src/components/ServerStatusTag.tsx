// 服务器在线状态（未采集/在线/离线三态）— 多页面复用
import { Tag } from 'antd'
import type { CollectData } from '../api/types'

/** 从采集缓存判断服务器状态 */
export function serverStatus(data?: CollectData | null): 'none' | 'online' | 'offline' {
  if (!data) return 'none'
  return data.status === 'offline' ? 'offline' : 'online'
}

/** 状态标签：🟢在线 / 🔴离线 / ⚪未采集（showNone=false 时不显示未采集） */
export default function ServerStatusTag({ data, showNone = true }: { data?: CollectData | null; showNone?: boolean }) {
  const st = serverStatus(data)
  if (st === 'offline') return <Tag color="red">离线</Tag>
  if (st === 'online') return <Tag color="green">在线</Tag>
  return showNone ? <Tag>未采集</Tag> : null
}

/** 服务器选项 label 后缀（"· 离线"），用于下拉/列表选项 */
export function offlineSuffix(data?: CollectData | null): string {
  return serverStatus(data) === 'offline' ? ' · 离线' : ''
}
