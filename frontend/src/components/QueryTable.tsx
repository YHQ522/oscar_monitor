// 通用查询结果表格：展示 columns/rows，支持错误态与导出
import { Table, Tag, Button, Space } from 'antd'
import { DownloadOutlined } from '@ant-design/icons'
import type { QueryResult } from '../api/types'

interface Props {
  result?: QueryResult
  title?: string
  onExport?: (result: QueryResult) => void
}

export default function QueryTable({ result, title, onExport }: Props) {
  if (!result) return null

  if (result.error) {
    return (
      <Tag color="error" style={{ whiteSpace: 'pre-wrap', maxWidth: '100%' }}>
        {result.error}
      </Tag>
    )
  }

  const columns = (result.columns || []).map((col, i) => ({
    title: col,
    dataIndex: i.toString(),
    key: i.toString(),
    ellipsis: true,
  }))

  const dataSource = (result.rows || []).map((row, ri) => {
    const rec: Record<string, string> = { key: String(ri) }
    row.forEach((v, ci) => {
      rec[ci.toString()] = v ?? ''
    })
    return rec
  })

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        {title && <span style={{ fontWeight: 600 }}>{title}</span>}
        {(onExport || result.columns?.length) && (
          <Space size={4}>
            {result.columns?.length > 0 && (
              <Button
                size="small"
                icon={<DownloadOutlined />}
                onClick={() => {
                  if (onExport) {
                    onExport(result)
                  } else {
                    // 默认导出为 CSV
                    const csv = [
                      result.columns.join(','),
                      ...(result.rows || []).map((r) => r.map((v) => `"${String(v ?? '').replace(/"/g, '""')}"`).join(',')),
                    ].join('\n')
                    const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8' })
                    const url = URL.createObjectURL(blob)
                    const a = document.createElement('a')
                    a.href = url
                    a.download = `${title || 'result'}.csv`
                    a.click()
                    URL.revokeObjectURL(url)
                  }
                }}
              >
                导出
              </Button>
            )}
          </Space>
        )}
      </div>
      {columns.length === 0 ? (
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
    </div>
  )
}
