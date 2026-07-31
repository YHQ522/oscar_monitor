// 启停管控页：数据库服务 + 应用分组管控
import { useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { Card, Button, Tag, Space, Spin, Empty, Popconfirm, Modal } from 'antd'
import { App as AntApp } from 'antd'
import { PoweroffOutlined, PlayCircleOutlined, ReloadOutlined, StopOutlined, EyeOutlined } from '@ant-design/icons'
import { api } from '../api/client'
import { useAuth } from '../store/auth'
import type { Server } from '../api/types'

interface ControlResp {
  ok: boolean
  msg: string
  action?: string
  running?: boolean
  output?: string
}

function ControlButton({ action, onClick, disabled }: { action: string; onClick: () => void; disabled: boolean }) {
  const map: Record<string, { icon: ReactNode; color: 'green' | 'red' | 'orange' | 'blue'; label: string }> = {
    start: { icon: <PlayCircleOutlined />, color: 'green', label: '启动' },
    stop: { icon: <StopOutlined />, color: 'red', label: '停止' },
    restart: { icon: <ReloadOutlined />, color: 'orange', label: '重启' },
    status: { icon: <EyeOutlined />, color: 'blue', label: '状态' },
  }
  const m = map[action]
  return (
    <Button size="small" icon={m.icon} color={m.color} variant="outlined" disabled={disabled} onClick={onClick}>
      {m.label}
    </Button>
  )
}

export default function ControlPage() {
  const user = useAuth((s) => s.user)
  const { message } = AntApp.useApp()
  const [servers, setServers] = useState<Server[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState<string | null>(null)
  const [modal, setModal] = useState<{ title: string; content: string } | null>(null)

  const canExec = user?.is_admin || user?.perms.includes('control_exec')

  useEffect(() => {
    api.get<Server[]>('/api/servers')
      .then((list) => setServers(list.filter((s) => s.in_control)))
      .catch((e) => message.error(e.message))
      .finally(() => setLoading(false))
  }, [])

  const run = async (server: Server, kind: 'db' | 'app', action: string, appName?: string) => {
    setBusy(`${server.id}-${kind}-${appName || 'db'}-${action}`)
    try {
      const body = appName ? { action, app: appName } : { action }
      const resp = await api.post<ControlResp>(
        `/api/servers/${server.id}/${kind === 'db' ? 'db-control' : 'app-control'}`,
        body,
      )
      if (resp.ok) {
        message.success(resp.msg)
      } else {
        message.error(resp.msg)
      }
      if (resp.output) {
        setModal({ title: `${server.name} - ${action} 输出`, content: resp.output })
      }
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setBusy(null)
    }
  }

  const groups = useMemo(() => {
    const g: Record<string, { server: Server; app: Server['apps'][number] }[]> = {}
    for (const s of servers) {
      for (const app of s.apps || []) {
        if (!app.in_control) continue
        const key = app.group || '其他应用'
        ;(g[key] = g[key] || []).push({ server: s, app })
      }
    }
    return g
  }, [servers])

  if (loading) {
    return <div style={{ textAlign: 'center', padding: 80 }}><Spin size="large" /></div>
  }

  if (!servers.length) {
    return <Empty description="暂无启用管控的服务器" />
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <h2 style={{ margin: 0 }}>启停管控</h2>

      <Card title="数据库服务" size="small">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {servers.filter((s) => !s.skip_db).length === 0 && (
            <Empty description="暂无数据库服务（仅系统监控的服务器无需数据库启停）" />
          )}
          {servers.filter((s) => !s.skip_db).map((s) => (
            <div key={s.id} style={{ display: 'flex', flexWrap: 'wrap', gap: 8, justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #f0f0f0', paddingBottom: 8 }}>
              <Space>
                <Tag color="purple">{s.db_type.toUpperCase()}</Tag>
                <b>{s.name}</b>
                <span style={{ color: '#8a94a6', fontSize: 12 }}>{s.ssh_host}</span>
              </Space>
              <Space wrap>
                <ControlButton
                  action="status"
                  disabled={busy !== null}
                  onClick={() => run(s, 'db', 'status')}
                />
                {canExec && (
                  <>
                    <ControlButton action="start" disabled={busy !== null} onClick={() => run(s, 'db', 'start')} />
                    <ControlButton action="stop" disabled={busy !== null} onClick={() => run(s, 'db', 'stop')} />
                    <Popconfirm title={`确认重启 ${s.name} 的数据库服务？`} onConfirm={() => run(s, 'db', 'restart')}>
                      <ControlButton action="restart" disabled={busy !== null} onClick={() => {}} />
                    </Popconfirm>
                  </>
                )}
              </Space>
            </div>
          ))}
        </div>
      </Card>

      {Object.entries(groups).map(([group, items]) => (
        <Card key={group} title={`应用组：${group}`} size="small">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {items.map(({ server, app }) => (
              <div key={`${server.id}-${app.name}`} style={{ display: 'flex', flexWrap: 'wrap', gap: 8, justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #f0f0f0', paddingBottom: 8 }}>
                <Space>
                  <Tag>{server.name}</Tag>
                  <b>{app.name}</b>
                  <span style={{ color: '#8a94a6', fontSize: 12 }}>端口 {app.port}</span>
                </Space>
                <Space wrap>
                  <ControlButton
                    action="status"
                    disabled={busy !== null}
                    onClick={() => run(server, 'app', 'status', app.name)}
                  />
                  {canExec && (
                    <>
                      <ControlButton action="start" disabled={busy !== null} onClick={() => run(server, 'app', 'start', app.name)} />
                      <ControlButton action="stop" disabled={busy !== null} onClick={() => run(server, 'app', 'stop', app.name)} />
                      <Popconfirm title={`确认重启 ${app.name}？`} onConfirm={() => run(server, 'app', 'restart', app.name)}>
                        <ControlButton action="restart" disabled={busy !== null} onClick={() => {}} />
                      </Popconfirm>
                    </>
                  )}
                </Space>
              </div>
            ))}
          </div>
        </Card>
      ))}

      <Modal
        title={modal?.title}
        open={!!modal}
        onCancel={() => setModal(null)}
        footer={null}
        width={720}
      >
        <pre className="mono" style={{ whiteSpace: 'pre-wrap', background: '#0f172a', color: '#e2e8f0', padding: 12, borderRadius: 8, maxHeight: 480, overflow: 'auto' }}>
          {modal?.content}
        </pre>
      </Modal>
    </div>
  )
}
