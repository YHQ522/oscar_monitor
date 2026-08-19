// 数据库错误日志面板：级别筛选 + 最新在前表格（数据已按时间倒序）
import { useMemo, useState } from 'react'
import { Empty, Radio, Table, Tag } from 'antd'
import type { QueryResult } from '../api/types'

const LEVEL_COLOR: Record<string, string> = {
  ERROR: 'red',
  FATAL: 'red',
  PANIC: 'magenta',
  WARNING: 'orange',
  NOTICE: 'blue',
  LOG: 'default',
}

type FilterMode = 'all' | 'err' | 'warn'

export default function DbLogErrorsPanel({ result }: { result?: QueryResult }) {
  const [filter, setFilter] = useState<FilterMode>('err')
  const cols = result?.columns || []
  const rows = result?.rows || []
  const idx = {
    file: cols.indexOf('文件'),
    time: cols.indexOf('时间'),
    level: cols.indexOf('级别'),
    msg: cols.indexOf('内容'),
  }

  const filtered = useMemo(() => {
    return rows.filter((r) => {
      const lv = String(r[idx.level] ?? '').toUpperCase()
      if (filter === 'all') return true
      if (filter === 'err') return ['ERROR', 'FATAL', 'PANIC'].includes(lv)
      return lv === 'WARNING'
    })
  }, [rows, filter, idx.level])

  if (!rows.length) {
    return <Empty description="暂无错误日志（采集范围：最近时间窗内的 ERROR/FATAL/WARNING）" image={Empty.PRESENTED_IMAGE_SIMPLE} />
  }

  return (
    <div>
      <div style={{ marginBottom: 8 }}>
        <Radio.Group value={filter} onChange={(e) => setFilter(e.target.value)} size="small">
          <Radio.Button value="err">错误（ERROR/FATAL/PANIC）</Radio.Button>
          <Radio.Button value="warn">警告（WARNING）</Radio.Button>
          <Radio.Button value="all">全部</Radio.Button>
        </Radio.Group>
        <span style={{ color: '#8a94a6', fontSize: 12, marginLeft: 12 }}>共 {filtered.length} 条</span>
      </div>
      {filtered.length === 0 ? (
        <Empty description="该级别暂无记录" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : (
        <div className="table-scroll">
          <Table
            size="small"
            rowKey={(r, i) => String(i)}
            dataSource={filtered}
            pagination={{ pageSize: 20, showSizeChanger: false }}
            scroll={{ x: 'max-content' }}
            columns={[
              {
                title: '时间',
                width: 170,
                render: (_: unknown, r: string[]) => <span style={{ fontFamily: 'Consolas, monospace', fontSize: 12 }}>{r[idx.time]}</span>,
              },
              {
                title: '级别',
                width: 90,
                render: (_: unknown, r: string[]) => {
                  const lv = String(r[idx.level] ?? '')
                  return lv ? <Tag color={LEVEL_COLOR[lv] || 'default'}>{lv}</Tag> : null
                },
              },
              {
                title: '文件',
                width: 200,
                ellipsis: true,
                render: (_: unknown, r: string[]) => <span style={{ fontSize: 12 }}>{r[idx.file]}</span>,
              },
              {
                title: '内容',
                ellipsis: true,
                render: (_: unknown, r: string[]) => <span style={{ fontFamily: 'Consolas, monospace', fontSize: 12 }}>{r[idx.msg]}</span>,
              },
            ]}
          />
        </div>
      )}
    </div>
  )
}
