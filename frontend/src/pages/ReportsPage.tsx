// 巡检报表：选择服务器与内容导出 Excel，管理导出历史
import { useEffect, useMemo, useState } from 'react'
import {
  Card, Checkbox, Button, Space, Table, Select, Radio, Popconfirm, Empty,
} from 'antd'
import { App as AntApp } from 'antd'
import { FileExcelOutlined, DeleteOutlined } from '@ant-design/icons'
import { api, downloadFile } from '../api/client'
import type { Server, ExportHistoryItem } from '../api/types'
import { useServerCache } from '../hooks/useSSE'

const CATEGORIES = [
  { id: 'basic_info', label: '基础信息' },
  { id: 'db_info', label: '数据库信息' },
  { id: 'storage', label: '存储空间' },
  { id: 'objects', label: '对象统计' },
  { id: 'performance', label: '性能监控' },
  { id: 'install_path', label: '安装路径' },
  { id: 'db_log_errors', label: '数据库日志' },
]

const OS_CHECKS = [
  { id: 'memory', label: '系统内存' },
  { id: 'disk', label: '系统磁盘' },
  { id: 'cpu', label: 'CPU负载' },
  { id: 'os_errors', label: '系统日志错误' },
]

export default function ReportsPage() {
  const { message } = AntApp.useApp()
  const cache = useServerCache()
  const [servers, setServers] = useState<Server[]>([])
  const [selected, setSelected] = useState<string[]>([])
  const [categories, setCategories] = useState<string[]>(['basic_info', 'performance'])
  const [osChecks, setOsChecks] = useState<string[]>(['memory', 'cpu'])
  const [organizeBy, setOrganizeBy] = useState('server')
  const [history, setHistory] = useState<ExportHistoryItem[]>([])
  const [exporting, setExporting] = useState(false)

  const load = async () => {
    try {
      const [s, h] = await Promise.all([
        api.get<Server[]>('/api/servers'),
        api.get<ExportHistoryItem[]>('/api/export/history'),
      ])
      setServers(s)
      setHistory(h)
    } catch (e) {
      message.error((e as Error).message)
    }
  }

  useEffect(() => {
    load()
  }, [])

  // 所选服务器是否全部为仅系统监控（无数据库数据可导出）
  const allSkipDb = useMemo(
    () => selected.length > 0 && selected.every((sid) => servers.find((s) => s.id === sid)?.skip_db),
    [selected, servers],
  )
  // 所选服务器中处于离线的台数
  const offlineSelected = useMemo(
    () => selected.filter((sid) => cache[sid]?.status === 'offline'),
    [selected, cache],
  )

  const doExport = async () => {
    if (!selected.length) {
      message.warning('请选择至少一台服务器')
      return
    }
    if (!categories.length && !osChecks.length) {
      message.warning('请选择至少一项导出内容')
      return
    }
    setExporting(true)
    const hideLoading = message.loading('正在生成巡检报告，请稍候...', 0)
    try {
      const resp = await fetch('/api/export/xlsx', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${localStorage.getItem('oscar_token') || ''}`,
        },
        body: JSON.stringify({
          servers: selected,
          categories,
          os_checks: osChecks,
          organize_by: organizeBy,
        }),
      })
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}))
        throw new Error((data as { detail?: string }).detail || '导出失败')
      }
      const blob = await resp.blob()
      const filename = resp.headers.get('X-Filename')
        ? decodeURIComponent(resp.headers.get('X-Filename')!)
        : '巡检报告.xlsx'
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      a.click()
      URL.revokeObjectURL(url)
      hideLoading()
      message.success('导出成功')
      load()
    } catch (e) {
      hideLoading()
      message.error((e as Error).message)
    } finally {
      setExporting(false)
    }
  }

  const removeHistory = async (filename: string) => {
    try {
      await api.delete(`/api/export/history/${filename}`)
      message.success('已删除')
      load()
    } catch (e) {
      message.error((e as Error).message)
    }
  }

  const historyColumns = [
    { title: '文件名', dataIndex: 'filename' },
    { title: '服务器数', dataIndex: 'server_count', width: 90 },
    { title: '内容项', dataIndex: 'item_count', width: 90 },
    { title: '大小', dataIndex: 'size_str', width: 90 },
    { title: '时间', dataIndex: 'time' },
    {
      title: '操作',
      width: 160,
      render: (_: unknown, r: ExportHistoryItem) => (
        <Space>
          <Button size="small" onClick={() => downloadFile(`/api/export/download/${r.filename}`, r.filename)}>下载</Button>
          <Popconfirm title="确认删除该历史文件？" onConfirm={() => removeHistory(r.filename)}>
            <Button size="small" danger icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <h2 style={{ margin: 0 }}>巡检报表</h2>

      <Card title="导出配置" size="small">
        <div style={{ marginBottom: 16 }}>
          <div style={{ fontWeight: 600, marginBottom: 8 }}>选择服务器</div>
          <Select
            mode="multiple"
            style={{ width: '100%' }}
            placeholder="选择要导出的服务器"
            value={selected}
            onChange={setSelected}
            options={servers.map((s) => ({ value: s.id, label: `${s.name}${cache[s.id]?.status === 'offline' ? ' · 离线' : ''}` }))}
          />
          {offlineSelected.length > 0 && (
            <div style={{ color: '#d97706', fontSize: 12, background: 'rgba(217,119,6,0.08)', border: '1px solid rgba(217,119,6,0.3)', borderRadius: 8, padding: '6px 10px', marginTop: 8 }}>
              ⚠️ 已选中 {offlineSelected.length} 台离线服务器，导出的报告内容可能为空或不完整
            </div>
          )}
        </div>

        <div style={{ marginBottom: 16 }}>
          <div style={{ fontWeight: 600, marginBottom: 8 }}>数据库采集类别</div>
          {allSkipDb && (
            <div style={{ color: '#888', marginBottom: 8 }}>所选服务器均为「仅系统」监控，无数据库数据可导出。</div>
          )}
          <Checkbox.Group
            options={CATEGORIES.map((c) => ({ value: c.id, label: c.label }))}
            value={categories}
            onChange={(v) => setCategories(v as string[])}
            disabled={allSkipDb}
          />
        </div>

        <div style={{ marginBottom: 16 }}>
          <div style={{ fontWeight: 600, marginBottom: 8 }}>系统检查项</div>
          <Checkbox.Group
            options={OS_CHECKS.map((c) => ({ value: c.id, label: c.label }))}
            value={osChecks}
            onChange={(v) => setOsChecks(v as string[])}
          />
        </div>

        <div style={{ marginBottom: 16 }}>
          <div style={{ fontWeight: 600, marginBottom: 8 }}>组织方式</div>
          <Radio.Group value={organizeBy} onChange={(e) => setOrganizeBy(e.target.value)}>
            <Radio.Button value="server">按服务器</Radio.Button>
            <Radio.Button value="category">按类别</Radio.Button>
          </Radio.Group>
        </div>

        <Button type="primary" icon={<FileExcelOutlined />} onClick={doExport} loading={exporting}>
          生成 Excel 巡检报告
        </Button>
      </Card>

      <Card title={`导出历史 (${history.length})`} size="small">
        {history.length === 0 ? (
          <Empty description="暂无导出历史" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : (
          <Table rowKey="filename" dataSource={history} columns={historyColumns} pagination={false} scroll={{ x: 'max-content' }} />
        )}
      </Card>
    </div>
  )
}
