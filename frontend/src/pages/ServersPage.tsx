// 服务管理列表
import { useEffect, useMemo, useState } from 'react'
import { Table, Button, Space, Tag, Popconfirm, Typography, Input, Select } from 'antd'
import { App as AntApp } from 'antd'
import { PlusOutlined, EditOutlined, DeleteOutlined, EyeOutlined, DatabaseOutlined, SearchOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { useServerCache } from '../hooks/useSSE'
import { useAuth } from '../store/auth'
import type { Server } from '../api/types'

export default function ServersPage() {
  const navigate = useNavigate()
  const user = useAuth((s) => s.user)
  const { message } = AntApp.useApp()
  const cache = useServerCache()
  const [servers, setServers] = useState<Server[]>([])
  const [loading, setLoading] = useState(true)
  const [kw, setKw] = useState('')
  const [dbType, setDbType] = useState<string>()

  const canEdit = user?.is_admin || user?.perms.includes('servers_edit')

  const filtered = useMemo(() => {
    let list = servers
    if (kw) {
      const k = kw.toLowerCase()
      list = list.filter(
        (s) =>
          (s.name || '').toLowerCase().includes(k) ||
          (s.ssh_host || '').toLowerCase().includes(k) ||
          (s.db_host || '').toLowerCase().includes(k),
      )
    }
    if (dbType === '__skip_db__') list = list.filter((s) => s.skip_db)
    else if (dbType) list = list.filter((s) => s.db_type === dbType)
    return list
  }, [servers, kw, dbType])

  const dbTypeOptions = useMemo(() => {
    const set = new Set(servers.map((s) => s.db_type))
    const opts = Array.from(set).map((t) => ({ value: t, label: t.toUpperCase() }))
    if (servers.some((s) => s.skip_db)) opts.push({ value: '__skip_db__', label: '仅系统' })
    return opts
  }, [servers])

  const load = async () => {
    setLoading(true)
    try {
      setServers(await api.get<Server[]>('/api/servers'))
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const remove = async (server: Server) => {
    try {
      await api.delete(`/api/servers/${server.id}`)
      message.success(`已删除 ${server.name}`)
      load()
    } catch (e) {
      message.error((e as Error).message)
    }
  }

  const columns = [
    {
      title: '名称',
      dataIndex: 'name',
      render: (v: string, r: Server) => (
        <Space>
          <DatabaseOutlined style={{ color: '#4f46e5' }} />
          <Typography.Link onClick={() => navigate(`/server/${r.id}`)}>{v}</Typography.Link>
        </Space>
      ),
    },
    {
      title: '数据库类型',
      dataIndex: 'db_type',
      render: (v: string, r: Server) => (r.skip_db ? <Tag>—</Tag> : <Tag color="blue">{v.toUpperCase()}</Tag>),
    },
    {
      title: '状态',
      width: 90,
      render: (_: unknown, r: Server) => {
        const d = cache[r.id]
        if (!d) return <Tag>未采集</Tag>
        return d.status === 'offline' ? <Tag color="red">离线</Tag> : <Tag color="green">在线</Tag>
      },
    },
    { title: 'SSH 地址', render: (_: unknown, r: Server) => `${r.ssh_host}:${r.ssh_port}` },
    { title: '数据库地址', render: (_: unknown, r: Server) => (r.skip_db ? '—' : `${r.db_host}:${r.db_port}`) },
    {
      title: '采集范围',
      render: (_: unknown, r: Server) => {
        const cats = r.enabled_categories || []
        const os = r.enabled_os_checks || []
        const hasDb = cats.length > 0
        const hasOs = os.length > 0
        if (r.skip_db || (!hasDb && hasOs)) return <Tag color="green">仅系统</Tag>
        if (hasDb && !hasOs) return <Tag color="purple">仅数据库</Tag>
        if (hasDb && hasOs) return <Tag color="blue">系统+数据库</Tag>
        return <Tag>未配置</Tag>
      },
    },
    {
      title: '管控',
      render: (_: unknown, r: Server) => (
        <Space>
          <Tag color={r.in_control ? 'green' : 'default'}>{r.in_control ? '启用' : '停用'}</Tag>
          {r.persist_enabled && <Tag color="purple">日志持久化</Tag>}
        </Space>
      ),
    },
    {
      title: '操作',
      fixed: 'right' as const,
      width: 220,
      render: (_: unknown, r: Server) => (
        <Space>
          <Button size="small" icon={<EyeOutlined />} onClick={() => navigate(`/server/${r.id}`)}>详情</Button>
          {canEdit && (
            <>
              <Button size="small" icon={<EditOutlined />} onClick={() => navigate(`/servers/add?edit=${r.id}`)}>编辑</Button>
              <Popconfirm title={`确认删除 ${r.name}？`} onConfirm={() => remove(r)}>
                <Button size="small" danger icon={<DeleteOutlined />}>删除</Button>
              </Popconfirm>
            </>
          )}
        </Space>
      ),
    },
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16, gap: 12, flexWrap: 'wrap' }}>
        <h2 style={{ margin: 0 }}>服务管理</h2>
        <Space wrap>
          <Input
            allowClear
            prefix={<SearchOutlined />}
            placeholder="搜索名称 / SSH / 数据库地址"
            style={{ width: 240 }}
            value={kw}
            onChange={(e) => setKw(e.target.value)}
          />
          <Select
            allowClear
            placeholder="数据库类型"
            style={{ width: 140 }}
            value={dbType}
            onChange={setDbType}
            options={dbTypeOptions}
          />
          {canEdit && (
            <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate('/servers/add')}>
              添加服务器
            </Button>
          )}
        </Space>
      </div>
      <Table
        rowKey="id"
        loading={loading}
        dataSource={filtered}
        columns={columns}
        pagination={{ pageSize: 10, showSizeChanger: true, showTotal: (t) => `共 ${t} 台` }}
        scroll={{ x: 'max-content' }}
      />
    </div>
  )
}
