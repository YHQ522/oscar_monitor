// 磁盘使用率：解析 df 输出为进度条列表
import { useMemo } from 'react'
import { Empty, Progress } from 'antd'
import type { QueryResult } from '../api/types'

export default function DiskUsage({ result }: { result?: QueryResult }) {
  const items = useMemo(() => {
    if (!result?.rows?.length) return []
    const cols = result.columns || []
    const pctIdx = cols.findIndex((c) => /使用率|占用率|已用%|use%|used%/i.test(String(c)))
    const nameIdx = cols.findIndex((c) => /文件系统|filesystem|挂载点|mounted|name|盘符|drive|letter/i.test(String(c)))
    if (pctIdx < 0) return []
    return result.rows
      .map((row) => {
        const raw = String(row[pctIdx] || '')
        const m = raw.match(/([\d.]+)/)
        return {
          name: nameIdx >= 0 ? String(row[nameIdx] || '') : raw,
          pct: m ? Number(m[1]) : 0,
        }
      })
      .filter((x) => x.pct > 0)
  }, [result])

  if (!items.length) {
    return <Empty description="暂无磁盘数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {items.map((it, idx) => (
        <div key={`${it.name}-${idx}`}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 2 }}>
            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{it.name}</span>
            <span>{it.pct}%</span>
          </div>
          <Progress
            percent={Math.min(100, it.pct)}
            size="small"
            strokeColor={it.pct >= 90 ? '#f5222d' : it.pct >= 75 ? '#faad14' : '#4f46e5'}
            showInfo={false}
          />
        </div>
      ))}
    </div>
  )
}
