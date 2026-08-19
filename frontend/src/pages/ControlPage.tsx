// 启停管控页：数据库服务 + 应用分组管控
import { useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { Card, Button, Tag, Space, Spin, Empty, Modal } from 'antd'
import { App as AntApp } from 'antd'
import { PlayCircleOutlined, ReloadOutlined, StopOutlined, EyeOutlined } from '@ant-design/icons'
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
  const { message, modal } = AntApp.useApp()
  const [servers, setServers] = useState<Server[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState<string | null>(null)
  const [outputModal, setOutputModal] = useState<{ title: string; content: string } | null>(null)
  // 各服务/应用当前运行状态：key = db:<serverId> 或 app:<serverId>:<appName>
  const [runningMap, setRunningMap] = useState<Record<string, boolean>>({})

  const canExec = user?.is_admin || user?.perms.includes('control_exec')

  const keyOf = (server: Server, kind: 'db' | 'app', appName?: string) =>
    kind === 'db' ? `db:${server.id}` : `app:${server.id}:${appName}`

  // 静默查询状态（不弹消息/输出框）
  const silentStatus = async (server: Server, kind: 'db' | 'app', appName?: string) => {
    try {
      const body = appName ? { action: 'status', app: appName } : { action: 'status' }
      const resp = await api.post<ControlResp>(
        `/api/servers/${server.id}/${kind === 'db' ? 'db-control' : 'app-control'}`,
        body,
      )
      if (typeof resp.running === 'boolean') {
        setRunningMap((m) => ({ ...m, [keyOf(server, kind, appName)]: resp.running! }))
      }
    } catch {
      /* 静默失败：保持未知状态 */
    }
  }

  useEffect(() => {
    api.get<Server[]>('/api/servers')
      .then((list) => {
        const srv = list.filter((s) => s.in_control)
        setServers(srv)
        // 初始加载各服务/应用的运行状态
        srv.forEach((s) => {
          if (!s.skip_db) silentStatus(s, 'db')
          for (const app of s.apps || []) {
            if (app.in_control) silentStatus(s, 'app', app.name)
          }
        })
      })
      .catch((e) => message.error(e.message))
      .finally(() => setLoading(false))
  }, [])

  const run = async (server: Server, kind: 'db' | 'app', action: string, appName?: string) => {
    const key = keyOf(server, kind, appName)
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
        setOutputModal({ title: `${server.name} - ${action} 输出`, content: resp.output })
      }
      // 更新本地运行状态：优先用返回的 running；无则按动作推断；随后静默复查
      if (typeof resp.running === 'boolean') {
        setRunningMap((m) => ({ ...m, [key]: resp.running! }))
      } else if (action === 'start' || action === 'restart') {
        setRunningMap((m) => ({ ...m, [key]: true }))
      } else if (action === 'stop') {
        setRunningMap((m) => ({ ...m, [key]: false }))
      }
      if (action !== 'status') silentStatus(server, kind, appName)
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setBusy(null)
    }
  }

  // 启动/停止/重启统一入口：先做状态提示，再二次确认
  const confirmAction = (server: Server, kind: 'db' | 'app', action: string, appName?: string) => {
    const key = keyOf(server, kind, appName)
    const running = runningMap[key]
    const target = appName ? `应用「${appName}」` : '数据库服务'

    if (action === 'start' && running === true) {
      message.warning(`${target}已在运行中，无需重复启动`)
      return
    }
    if (action === 'stop' && running === false) {
      message.warning(`${target}已处于停止状态，无需重复停止`)
      return
    }

    const isStop = action === 'stop'
    const actionLabel = action === 'start' ? '启动' : action === 'stop' ? '停止' : '重启'
    const stateHint = running === true ? '（当前状态：运行中）' : running === false ? '（当前状态：已停止）' : ''
    const restartStopped = action === 'restart' && running === false
    modal.confirm({
      title: `确认${actionLabel} ${target}？`,
      content: `即将对 ${server.name} 的${target}执行${actionLabel}操作${stateHint}。${restartStopped ? '服务当前已停止，重启操作将尝试拉起服务。' : ''}${isStop ? '停止服务期间相关业务将中断，请谨慎操作。' : ''}`,
      okText: actionLabel,
      okButtonProps: isStop ? { danger: true } : undefined,
      cancelText: '取消',
      onOk: () => run(server, kind, action, appName),
    })
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
                    <ControlButton action="start" disabled={busy !== null} onClick={() => confirmAction(s, 'db', 'start')} />
                    <ControlButton action="stop" disabled={busy !== null} onClick={() => confirmAction(s, 'db', 'stop')} />
                    <ControlButton action="restart" disabled={busy !== null} onClick={() => confirmAction(s, 'db', 'restart')} />
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
                      <ControlButton action="start" disabled={busy !== null} onClick={() => confirmAction(server, 'app', 'start', app.name)} />
                      <ControlButton action="stop" disabled={busy !== null} onClick={() => confirmAction(server, 'app', 'stop', app.name)} />
                      <ControlButton action="restart" disabled={busy !== null} onClick={() => confirmAction(server, 'app', 'restart', app.name)} />
                    </>
                  )}
                </Space>
              </div>
            ))}
          </div>
        </Card>
      ))}

      <Modal
        title={outputModal?.title}
        open={!!outputModal}
        onCancel={() => setOutputModal(null)}
        footer={null}
        width={720}
      >
        <pre className="mono" style={{ whiteSpace: 'pre-wrap', background: '#0f172a', color: '#e2e8f0', padding: 12, borderRadius: 8, maxHeight: 480, overflow: 'auto' }}>
          {outputModal?.content}
        </pre>
      </Modal>
    </div>
  )
}
