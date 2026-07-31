// 日志历史：服务器错误日志 / 慢 SQL 查询
import { useEffect, useState } from 'react'
import { Card, Table, Tag, Input, Select, Space, Button, Pagination, Empty } from 'antd'
import { App as AntApp } from 'antd'
import { SearchOutlined } from '@ant-design/icons'
import { useParams } from 'react-router-dom'
import { api } from '../api/client'
import type { Server, LogRecord } from '../api/types'

export default function LogHistoryPage() {
  const { id = '' } = useParams()
  const { message } = AntApp.useApp()
  const [server, setServer] = useState<Server | null>(null)
  const [logs, setLogs] = useState<LogRecord[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [kw, setKw] = useState('')
  const [type, setType] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    api.get<Server[]>('/api/servers')
      .then((list) => setServer(list.find((s) => s.id === id) || null))
      .catch(() => message.error('加载服务器失败'))
  }, [id])

  const load = async (p = page, k = kw, t = type) => {
    setLoading(true)
    try {
      const data = await api.get<{ logs: LogRecord[]; total: number }>(
        `/api/servers/${id}/log-errors?page=${p}&size=50&kw=${encodeURIComponent(k)}&type=${t}`,
      )
      setLogs(data.logs)
      setTotal(data.total)
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (id) load(1, '', '')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])

  const columns = [
    {
      title: '类型',
      dataIndex: 'check_type',
      width: 100,
      render: (v: string) =>
        v === 'slow_sql' ? <Tag color="orange">慢SQL</Tag> : v === 'db_error' ? <Tag color="red">DB错误</Tag> : <Tag color="blue">{v}</Tag>,
    },
    {
      title: '内容',
      dataIndex: 'error_msg',
      ellipsis: true,
      render: (v: string) => <span style={{ fontFamily: 'Consolas, monospace', fontSize: 12 }}>{v}</span>,
    },
    { title: '次数', dataIndex: 'occur_count', width: 70 },
    { title: '耗时(s)', dataIndex: 'cost_seconds', width: 90 },
    { title: '时间', dataIndex: 'occur_time', width: 160 },
  ]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <h2 style={{ margin: 0 }}>日志历史 {server ? `— ${server.name}` : ''}</h2>

      <Card size="small">
        <Space wrap>
          <Select
            style={{ width: 140 }}
            placeholder="日志类型"
            value={type || undefined}
            onChange={(v) => { setType(v); load(1, kw, v) }}
            allowClear
            options={[
              { value: 'slow_sql', label: '慢SQL' },
              { value: 'db_error', label: '数据库错误' },
              { value: 'os_errors', label: '系统错误' },
            ]}
          />
          <Input.Search
            placeholder="搜索内容"
            style={{ width: 260 }}
            value={kw}
            onChange={(e) => setKw(e.target.value)}
            onSearch={(v) => load(1, v, type)}
            enterButton={<SearchOutlined />}
          />
          <Button onClick={() => { setKw(''); setType(''); load(1, '', '') }}>重置</Button>
          <span style={{ color: '#8a94a6' }}>共 {total} 条</span>
        </Space>
      </Card>

      <Card size="small">
        {total === 0 && !loading ? (
          <Empty description="暂无日志记录（需启用日志持久化并采集）" />
        ) : (
          <Table rowKey={(r) => `${r.occur_time}-${r.error_msg?.slice(0, 24)}`} loading={loading} dataSource={logs} columns={columns} pagination={false} size="small" scroll={{ x: 'max-content' }} />
        )}
        {total > 50 && (
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 12 }}>
            <Pagination
              current={page}
              pageSize={50}
              total={total}
              onChange={(p) => { setPage(p); load(p, kw, type) }}
              showSizeChanger={false}
            />
          </div>
        )}
      </Card>
    </div>
  )
}
