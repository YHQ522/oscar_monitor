// 主布局：侧边导航 + 顶栏
import { useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { Layout as AntLayout, Menu, Avatar, Dropdown, theme, Button, Badge, Modal, Tag, Empty, Space } from 'antd'
import {
  DashboardOutlined,
  DatabaseOutlined,
  ControlOutlined,
  FileTextOutlined,
  UserOutlined,
  SettingOutlined,
  CodeOutlined,
  LogoutOutlined,
  ProfileOutlined,
  SunOutlined,
  MoonOutlined,
  BellOutlined,
} from '@ant-design/icons'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import type { Server, HealthScore } from '../api/types'
import { useAuth } from '../store/auth'
import { useThemeStore } from '../store/theme'
import { useCacheStore, collectAlerts } from '../store/cache'
import { useAlertSettings } from '../store/alerts'

const { Sider, Header, Content } = AntLayout

// 告警已读指纹：服务器 id + 错误内容（内容相同视为同一条告警）
const alertKey = (a: { id: string; error: string }) => `${a.id}:${a.error}`

export default function Layout() {
  const navigate = useNavigate()
  const location = useLocation()
  const user = useAuth((s) => s.user)
  const logout = useAuth((s) => s.logout)
  const mode = useThemeStore((s) => s.mode)
  const toggleTheme = useThemeStore((s) => s.toggle)
  const { token } = theme.useToken()
  // 侧边栏折叠状态（窄屏自动折叠为图标栏）
  const [siderCollapsed, setSiderCollapsed] = useState(false)

  // 告警：采集缓存中出现错误的服务器（过滤已静默项）
  const cacheData = useCacheStore((s) => s.data)
  const muted = useAlertSettings((s) => s.muted)
  const toggleMute = useAlertSettings((s) => s.toggleMute)
  const unmute = useAlertSettings((s) => s.unmute)
  // 健康分低告警：评分 < 60（与首页“异常”阈值一致）的服务器也计入铃铛
  const [healthAlerts, setHealthAlerts] = useState<{ id: string; name: string; error: string }[]>([])
  useEffect(() => {
    let cancelled = false
    const load = async () => {
      try {
        const [servers, scores] = await Promise.all([
          api.get<Server[]>('/api/servers'),
          api.get<Record<string, HealthScore>>('/api/health'),
        ])
        if (cancelled) return
        setHealthAlerts(
          servers
            .filter((s) => {
              const sc = scores[s.id]?.score
              return sc != null && sc < 60
            })
            .map((s) => ({
              id: s.id,
              name: s.name,
              error: `健康分 ${scores[s.id]?.score} 低于 60，请关注`,
            })),
        )
      } catch {
        /* ignore */
      }
    }
    load()
    const timer = setInterval(load, 30000)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [])

  const alerts = useMemo(() => {
    // 两类告警：采集错误 + 健康分低，合并并按服务器去重（采集错误优先）
    const errAlerts = collectAlerts(cacheData).filter((a) => !muted[a.id])
    const health = healthAlerts.filter((a) => !muted[a.id])
    const byId = new Map<string, { id: string; name: string; error: string }>()
    for (const a of errAlerts) byId.set(a.id, a)
    for (const a of health) if (!byId.has(a.id)) byId.set(a.id, a)
    return Array.from(byId.values())
  }, [cacheData, muted, healthAlerts])
  const [alertOpen, setAlertOpen] = useState(false)
  // 已读告警指纹集合：未读 = 当前告警中指纹未被标记已读的
  // 修复：按数量记录已读时，静默/恢复导致数量减少会误重置，已读告警重新变为未读
  const [readKeys, setReadKeys] = useState<Set<string>>(new Set())
  const unreadAlerts = useMemo(
    () => alerts.filter((a) => !readKeys.has(alertKey(a))),
    [alerts, readKeys],
  )
  const unreadCount = unreadAlerts.length

  const menuItems = useMemo(() => {
    const items: { key: string; icon: ReactNode; label: string }[] = []
    if (user?.is_admin || user?.perms.includes('dashboard')) {
      items.push({ key: '/', icon: <DashboardOutlined />, label: '全局监控' })
    }
    if (user?.is_admin || user?.perms.some((p) => ['servers_view', 'servers_edit'].includes(p))) {
      items.push({ key: '/servers', icon: <DatabaseOutlined />, label: '服务管理' })
    }
    if (user?.is_admin || user?.perms.some((p) => ['control_view', 'control_exec'].includes(p))) {
      items.push({ key: '/control', icon: <ControlOutlined />, label: '启停管控' })
    }
    if (user?.is_admin) {
      items.push({ key: '/reports', icon: <FileTextOutlined />, label: '巡检报表' })
      items.push({ key: '/sql-terminal', icon: <CodeOutlined />, label: 'SQL 终端' })
      items.push({ key: '/users', icon: <UserOutlined />, label: '用户管理' })
      items.push({ key: '/config', icon: <SettingOutlined />, label: '系统配置' })
    }
    return items
  }, [user])

  const selectedKey =
    location.pathname === '/' ? '/' : '/' + location.pathname.split('/')[1]

  return (
    <AntLayout style={{ height: '100vh', overflow: 'hidden' }}>
      <Sider
        theme="dark"
        width={200}
        breakpoint="lg"
        collapsedWidth={64}
        collapsed={siderCollapsed}
        onCollapse={setSiderCollapsed}
        style={{ overflow: 'auto', position: 'sticky', top: 0, height: '100vh' }}
      >
        <div
          style={{
            height: 56,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#fff',
            fontWeight: 700,
            fontSize: 15,
            gap: 8,
            overflow: 'hidden',
            whiteSpace: 'nowrap',
          }}
        >
          <img src="/favicon.svg" alt="logo" style={{ width: 26, height: 26, flexShrink: 0 }} />
          {!siderCollapsed && <span>数据库监控</span>}
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[selectedKey]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>
      <AntLayout>
        <Header
          style={{
            background: token.colorBgContainer,
            padding: '0 24px',
            display: 'flex',
            justifyContent: 'flex-end',
            alignItems: 'center',
            boxShadow: '0 1px 4px rgba(0,0,0,0.08)',
          }}
        >
          <Badge count={unreadCount} size="small" offset={[-2, 2]}>
            <Button
              type="text"
              icon={<BellOutlined />}
              onClick={() => { setAlertOpen(true); setReadKeys(new Set(alerts.map((a) => alertKey(a)))) }}
              title="采集告警"
              style={{ marginRight: 4 }}
            />
          </Badge>
          <Button
            type="text"
            icon={mode === 'dark' ? <SunOutlined /> : <MoonOutlined />}
            onClick={toggleTheme}
            style={{ marginRight: 8 }}
            title={mode === 'dark' ? '切换浅色模式' : '切换深色模式'}
          />
          <Dropdown
            menu={{
              items: [
                { key: 'profile', icon: <ProfileOutlined />, label: '个人中心', onClick: () => navigate('/profile') },
                { type: 'divider' },
                { key: 'logout', icon: <LogoutOutlined />, label: '退出登录', onClick: () => { logout(); navigate('/login') } },
              ],
            }}
          >
            <span style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8 }}>
              <Avatar size="small" style={{ background: token.colorPrimary }}>
                {(user?.username || '?').charAt(0).toUpperCase()}
              </Avatar>
              <span>{user?.username}</span>
              {user?.is_admin && <span style={{ fontSize: 12, color: token.colorTextSecondary }}>管理员</span>}
            </span>
          </Dropdown>
        </Header>
        <Content style={{ padding: 24, overflow: 'auto', background: token.colorBgLayout }}>
          <Outlet />
        </Content>
      </AntLayout>

      <Modal
        title={`采集告警 (${alerts.length})`}
        open={alertOpen}
        onCancel={() => setAlertOpen(false)}
        footer={null}
        width={560}
      >
        {alerts.length === 0 ? (
          <Empty description="当前无采集告警" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {alerts.map((a) => (
              <div key={a.id} style={{ border: '1px solid #f0f0f0', borderRadius: 8, padding: 10 }}>
                <Tag color="red">异常</Tag>
                <b>{a.name}</b>
                <div style={{ fontSize: 12, color: '#f5222d', marginTop: 4, wordBreak: 'break-all' }}>{a.error}</div>
                <Space style={{ marginTop: 4 }} wrap>
                  <Button type="link" size="small" onClick={() => { setAlertOpen(false); navigate(`/server/${a.id}`) }}>
                    查看详情
                  </Button>
                  <Button
                    type="link"
                    size="small"
                    danger
                    onClick={() => toggleMute(a.id, a.name)}
                    title="静默后该服务器不再产生告警"
                  >
                    静默
                  </Button>
                </Space>
              </div>
            ))}
          </div>
        )}
        {Object.keys(muted).length > 0 && (
          <div style={{ marginTop: 14, borderTop: '1px solid #f0f0f0', paddingTop: 10 }}>
            <div style={{ fontSize: 12, color: '#8a94a6', marginBottom: 6 }}>
              已静默的服务器（点击 × 恢复告警）：
            </div>
            {Object.entries(muted).map(([id, name]) => (
              <Tag key={id} closable onClose={() => unmute(id)} style={{ marginBottom: 4 }}>
                {name}
              </Tag>
            ))}
          </div>
        )}
      </Modal>
    </AntLayout>
  )
}
