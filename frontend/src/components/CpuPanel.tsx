// CPU 人性化展示：使用率仪表盘 + 概况 + 占用最高的进程表
import { Card, Progress, Row, Col, Table } from 'antd'
import type { QueryResult } from '../api/types'

interface CpuResult extends QueryResult {
  summary?: { label: string; value: string }[]
}

export default function CpuPanel({ result }: { result?: CpuResult }) {
  const summary = result?.summary || []
  const pct = (() => {
    const s = summary.find((x) => x.label === 'CPU 使用率')
    if (s) {
      const m = s.value.match(/([\d.]+)/)
      if (m) return Math.min(100, Number(m[1]))
    }
    return null
  })()

  const columns = (result?.columns || []).map((c, i) => ({
    title: c,
    dataIndex: i.toString(),
    key: i.toString(),
    ellipsis: true,
  }))
  const dataSource = (result?.rows || []).map((r, ri) => {
    const rec: Record<string, string> = { key: String(ri) }
    r.forEach((v, ci) => {
      rec[ci.toString()] = v ?? ''
    })
    return rec
  })

  return (
    <div>
      <Row gutter={[16, 16]}>
        <Col xs={24} md={8}>
          <Card size="small">
            <div style={{ textAlign: 'center' }}>
              <Progress
                type="dashboard"
                percent={pct ?? 0}
                strokeColor={pct != null && pct >= 80 ? '#f5222d' : pct != null && pct >= 60 ? '#faad14' : '#4f46e5'}
                format={() => (pct == null ? '—' : `${pct}%`)}
              />
              <div style={{ color: '#8a94a6', fontSize: 12, marginTop: 4 }}>CPU 使用率</div>
            </div>
          </Card>
        </Col>
        <Col xs={24} md={16}>
          <Card size="small" title="概况">
            {summary.length === 0 ? (
              <div style={{ color: '#94a3b8', padding: '8px 0' }}>（无数据）</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {summary.map((s) => (
                  <div key={s.label} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
                    <span style={{ color: '#8a94a6' }}>{s.label}</span>
                    <span style={{ fontWeight: 600 }}>{s.value}</span>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </Col>
      </Row>
      <Card size="small" title="CPU 占用最高的进程" style={{ marginTop: 12 }}>
        {dataSource.length === 0 ? (
          <div style={{ color: '#94a3b8', padding: '8px 0' }}>（无数据）</div>
        ) : (
          <div className="table-scroll">
            <Table
              size="small"
              columns={columns}
              dataSource={dataSource}
              pagination={dataSource.length > 20 ? { pageSize: 20, showSizeChanger: false } : false}
              scroll={{ x: 'max-content' }}
            />
          </div>
        )}
      </Card>
    </div>
  )
}
