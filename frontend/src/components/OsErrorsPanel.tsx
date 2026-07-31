// 操作系统日志错误人性化展示：时间 + 内容列表，错误码高亮，空态提示正常
import { Alert, List, Tag } from 'antd'
import type { QueryResult } from '../api/types'

interface OsErrorsResult extends QueryResult {
  output?: string
}

// 高亮 0x 错误码
function highlight(content: string) {
  const parts = content.split(/(0x[0-9a-fA-F]{4,})/g)
  return parts.map((p, i) =>
    /^0x[0-9a-fA-F]{4,}$/.test(p) ? (
      <span key={i} style={{ color: '#f5222d', fontWeight: 600, fontFamily: 'monospace' }}>{p}</span>
    ) : (
      <span key={i}>{p}</span>
    ),
  )
}

export default function OsErrorsPanel({ result }: { result?: OsErrorsResult }) {
  if (result?.error) {
    return (
      <Tag color="error" style={{ whiteSpace: 'pre-wrap', maxWidth: '100%' }}>
        {result.error}
      </Tag>
    )
  }
  if (!result?.output && !result?.rows?.length) {
    return (
      <Alert
        type="success"
        showIcon
        message="未发现系统错误日志"
        description="系统事件日志中没有 Error 级别记录，属正常状态。"
      />
    )
  }
  const rows = result?.rows || []
  return (
    <div>
      <div style={{ color: '#8a94a6', fontSize: 12, marginBottom: 8 }}>
        共 {rows.length} 条错误记录（最近 30 条）
      </div>
      <List
        size="small"
        dataSource={rows}
        renderItem={(row) => {
          const time = row[0] || '—'
          const content = row[1] || ''
          return (
            <List.Item style={{ padding: '10px 4px', borderBlockEnd: '1px solid #f0f0f0', alignItems: 'flex-start' }}>
              <div style={{ width: '100%', display: 'flex', gap: 12 }}>
                <span
                  style={{
                    fontFamily: 'monospace',
                    fontSize: 12,
                    color: '#8a94a6',
                    whiteSpace: 'nowrap',
                    paddingTop: 2,
                  }}
                >
                  {time}
                </span>
                <span style={{ fontSize: 13, color: '#333', flex: 1, lineHeight: 1.6 }}>{highlight(content)}</span>
              </div>
            </List.Item>
          )
        }}
      />
    </div>
  )
}
