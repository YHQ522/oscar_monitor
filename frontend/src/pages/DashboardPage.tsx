// 全局监控首页：玻璃拟态
import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import {
  Button, Space, Tag, Modal, Empty, Skeleton, Progress,
} from 'antd'
import { App as AntApp } from 'antd'
import {
  ReloadOutlined, EyeOutlined, DownloadOutlined, ThunderboltOutlined, PlusOutlined,
  CloudServerOutlined, CheckCircleOutlined, CloseCircleOutlined, DashboardOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { api, downloadFile } from '../api/client'
import { useServerCache } from '../hooks/useSSE'
import type { Server, HealthScore } from '../api/types'
import { useAuth } from '../store/auth'

function scoreColor(score: number | null): string {
  if (score == null) return '#cbd5e1'
  if (score >= 80) return '#059669'
  if (score >= 60) return '#6366f1'
  return '#ef4444'
}

// 进度条颜色（按使用率）
function barColor(p: number | null): string {
  if (p == null) return '#cbd5e1'
  if (p >= 80) return '#ef4444'
  if (p >= 60) return '#d97706'
  return '#059669'
}

// 解析 "18%" → 18
function parsePct(v: string | undefined): number | null {
  if (!v) return null
  const n = parseFloat(v)
  return Number.isNaN(n) ? null : n
}

// 解析 "3 条" / "0" → 数字
function parseCount(v: string | undefined): number {
  if (!v) return 0
  const n = parseInt(v, 10)
  return Number.isNaN(n) ? 0 : n
}

// 健康指标标签：与后端 health.details 的 key 对应
const DETAIL_LABELS: Record<string, string> = {
  cpu: 'CPU',
  memory: '内存',
  sessions: '连接数',
  slow_sql: '慢SQL',
  deadlocks: '死锁',
}

// 单项健康状态颜色（红黄绿）
const STATUS_COLORS: Record<string, string> = {
  healthy: '#059669',
  warning: '#d97706',
  danger: '#dc2626',
}

// 玻璃拟态样式常量
const GLASS_BG = 'rgba(255,255,255,0.6)'
const GLASS_BORDER = '1px solid rgba(255,255,255,0.7)'
const GLASS_SHADOW = '0 20px 50px rgba(99,102,241,0.14)'
const TEXT_SUB = '#94a3b8'
const TEXT_MAIN = '#1e293b'

// 页面背景：多彩渐变 + 光斑（玻璃拟态底）
const PAGE_BG: React.CSSProperties = {
  background: 'radial-gradient(circle at 15% 20%,rgba(129,140,248,0.35) 0%,transparent 45%),radial-gradient(circle at 85% 15%,rgba(34,211,238,0.28) 0%,transparent 40%),radial-gradient(circle at 75% 80%,rgba(244,114,182,0.28) 0%,transparent 45%),linear-gradient(135deg,#eef2ff,#fdf4ff)',
  borderRadius: 18,
  padding: 22,
}

// 玻璃卡片
function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div style={{ background: GLASS_BG, backdropFilter: 'blur(18px)', WebkitBackdropFilter: 'blur(18px)', border: GLASS_BORDER, borderRadius: 22, padding: '18px 22px', height: '100%', boxShadow: GLASS_SHADOW }}>
      <div style={{ fontSize: 14, fontWeight: 700, color: TEXT_MAIN, marginBottom: 14 }}>{title}</div>
      {children}
    </div>
  )
}

// 空态提示
function EmptyTip({ text = '暂无数据' }: { text?: string }) {
  return <div style={{ color: TEXT_SUB, textAlign: 'center', padding: '24px 0', fontSize: 13 }}>{text}</div>
}

// 状态呼吸灯 class
function dotClass(online: boolean, score: number | null): string {
  if (!online) return 'dash-dot dash-dot-gray'
  return score != null && score < 60 ? 'dash-dot dash-dot-red' : 'dash-dot dash-dot-green'
}

// 数据库类型 → 图标字母 + 渐变
function dbTypeMeta(s: Server): { label: string; grad: string } {
  if (s.skip_db) return { label: 'S', grad: 'linear-gradient(135deg,#94a3b8,#cbd5e1)' }
  switch (s.db_type) {
    case 'mysql': return { label: 'M', grad: 'linear-gradient(135deg,#10b981,#34d399)' }
    case 'postgresql': return { label: 'P', grad: 'linear-gradient(135deg,#f59e0b,#fbbf24)' }
    case 'oracle': return { label: 'O', grad: 'linear-gradient(135deg,#ef4444,#f97316)' }
    default: return { label: 'O', grad: 'linear-gradient(135deg,#6366f1,#8b5cf6)' }
  }
}

// 可点击数字样式
const CLICK_STYLE: React.CSSProperties = { cursor: 'pointer', fontWeight: 700, padding: '0 5px', borderRadius: 6, background: 'rgba(99,102,241,0.1)', color: '#6366f1' }

// 日志记录类型（慢SQL/死锁）
interface LogRow {
  check_type?: string
  error_msg?: string
  occur_count?: number
  occur_time?: string
  exec_user?: string
  exec_sql?: string
  cost_seconds?: number
}

export default function DashboardPage() {
  const navigate = useNavigate()
  const user = useAuth((s) => s.user)
  const { message } = AntApp.useApp()
  const cache = useServerCache()
  // 实时时钟（Hero 横幅右上角）
  const [now, setNow] = useState(new Date())
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(t)
  }, [])
  const pad2 = (n: number) => String(n).padStart(2, '0')
  const timeStr = `${pad2(now.getHours())}:${pad2(now.getMinutes())}:${pad2(now.getSeconds())}`
  const dateStr = `${now.getFullYear()}-${pad2(now.getMonth() + 1)}-${pad2(now.getDate())}`
  const [servers, setServers] = useState<Server[]>([])
  const [scores, setScores] = useState<Record<string, HealthScore>>({})
  const [loading, setLoading] = useState(false)
  const [collecting, setCollecting] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const loadServers = async () => {
    setLoading(true)
    try {
      // 列表与批量健康评分并行拉取（避免 N+1 请求）
      const [list, scoreMap] = await Promise.all([
        api.get<Server[]>('/api/servers'),
        api.get<Record<string, HealthScore>>('/api/health').catch(() => ({})),
      ])
      setServers(list)
      setScores(scoreMap)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadServers()
    // 定时刷新健康评分
    const timer = setInterval(loadServers, 30000)
    return () => clearInterval(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const collect = async (server: Server) => {
    setCollecting(server.id)
    try {
      await api.post(`/api/servers/${server.id}/collect`)
      message.success(`${server.name} 采集完成`)
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setCollecting(null)
    }
  }

  const collectAll = async () => {
    setLoading(true)
    try {
      await Promise.all(servers.map((s) => api.post(`/api/servers/${s.id}/collect`)))
      message.success('全部采集完成')
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  // ===== 慢SQL / 死锁详情弹窗 =====
  const [detail, setDetail] = useState<{ key: string; server: Server; type: 'slow' | 'dead'; logs: LogRow[]; loading: boolean } | null>(null)

  const openDetail = async (server: Server, type: 'slow' | 'dead') => {
    const key = `${server.id}:${type}`
    // 再次点击同一数字 → 无动作（弹窗保持打开）
    if (detail && detail.key === key) return
    setDetail({ key, server, type, logs: [], loading: true })
    try {
      const res = await api.get<{ logs: LogRow[] }>(
        `/api/servers/${server.id}/log-errors?log_type=${type === 'slow' ? 'slow_sql' : 'deadlock'}&size=30`,
      )
      setDetail({ key, server, type, logs: res.logs || [], loading: false })
    } catch {
      setDetail({ key, server, type, logs: [], loading: false })
    }
  }

  const canEdit = user?.is_admin || user?.perms.includes('servers_edit')

  // 概览统计
  const onlineCount = servers.filter((s) => cache[s.id]).length
  const abnormalCount = servers.filter((s) => {
    const sc = scores[s.id]?.score
    return sc != null && sc < 60
  }).length
  const validScores = servers
    .map((s) => scores[s.id]?.score)
    .filter((x): x is number => x != null)
  const avgScore = validScores.length
    ? Math.round(validScores.reduce((a, b) => a + b, 0) / validScores.length)
    : '—'

  // 健康分布统计（良好/关注/异常/未采集）
  const buckets = { good: 0, warn: 0, bad: 0, none: 0 }
  servers.forEach((s) => {
    const sc = scores[s.id]?.score
    if (sc == null) buckets.none++
    else if (sc >= 80) buckets.good++
    else if (sc >= 60) buckets.warn++
    else buckets.bad++
  })
  const pctOf = (n: number) => (servers.length ? Math.round((n / servers.length) * 100) : 0)

  // 按数据库类型统计服务器数量（含仅系统）
  const typeCounts: Record<string, number> = {}
  servers.forEach((s) => {
    const t = s.skip_db ? '仅系统' : (s.db_type || 'oscar')
    typeCounts[t] = (typeCounts[t] || 0) + 1
  })
  const TYPE_META: Record<string, { label: string; color: string }> = {
    oscar: { label: 'Oscar 神通', color: '#38bdf8' },
    mysql: { label: 'MySQL', color: '#4ade80' },
    postgresql: { label: 'PostgreSQL', color: '#fbbf24' },
    oracle: { label: 'Oracle', color: '#f87171' },
    '仅系统': { label: '仅系统监控', color: '#94a3b8' },
  }
  const offlineCount = servers.length - onlineCount
  // 数据库性能指标汇总
  const totalSessions = servers.reduce((a, s) => a + parseCount(scores[s.id]?.details?.sessions?.value), 0)
  const totalSlow = servers.reduce((a, s) => a + parseCount(scores[s.id]?.details?.slow_sql?.value), 0)
  const totalDead = servers.reduce((a, s) => a + parseCount(scores[s.id]?.details?.deadlocks?.value), 0)

  const thStyle: React.CSSProperties = { textAlign: 'left', color: TEXT_SUB, fontWeight: 600, padding: '8px', borderBottom: '1px solid #eef2f7', whiteSpace: 'nowrap' }
  const tdStyle: React.CSSProperties = { padding: '8px', borderBottom: '1px solid #f4f6fa', whiteSpace: 'nowrap' }

  return (
    <div style={PAGE_BG}>
      {error && <div style={{ color: '#dc2626', background: 'rgba(255,255,255,0.7)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: 10, padding: '8px 12px', marginBottom: 12, fontSize: 13 }}>{error}</div>}

      {/* ===== 顶栏 ===== */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '18px 24px', borderRadius: 22, marginBottom: 18, background: GLASS_BG, border: GLASS_BORDER, boxShadow: GLASS_SHADOW, flexWrap: 'wrap', gap: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <div style={{ width: 46, height: 46, borderRadius: 14, background: 'linear-gradient(135deg,#6366f1,#d946ef)', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 22, boxShadow: '0 8px 20px rgba(99,102,241,0.4)', flex: 'none' }}>🛰️</div>
          <div>
            <div style={{ fontSize: 20, fontWeight: 800, color: TEXT_MAIN }}>数据库监控</div>
            <div style={{ fontSize: 12, color: TEXT_SUB }}>Glass Monitoring Console</div>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
          <Space>
            <Button size="small" icon={<ReloadOutlined />} loading={loading} onClick={loadServers}>刷新</Button>
            {canEdit && <Button size="small" type="primary" icon={<PlusOutlined />} style={{ background: 'linear-gradient(135deg,#6366f1,#d946ef)', border: 'none' }} onClick={() => navigate('/servers/add')}>添加服务器</Button>}
            <Button size="small" icon={<ThunderboltOutlined />} disabled={!servers.length} onClick={collectAll}>全部采集</Button>
          </Space>
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontFamily: 'Consolas,monospace', fontSize: 22, fontWeight: 700, color: '#6366f1' }}>{timeStr}</div>
            <div style={{ fontSize: 12, color: TEXT_SUB }}>{dateStr}</div>
          </div>
        </div>
      </div>

      {/* ===== KPI 玻璃卡 ===== */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(160px,1fr))', gap: 16, marginBottom: 16 }}>
        {[
          { icon: <CloudServerOutlined />, label: '服务器总数', value: servers.length, grad: 'linear-gradient(135deg,#6366f1,#8b5cf6)' },
          { icon: <CheckCircleOutlined />, label: '在线运行', value: onlineCount, grad: 'linear-gradient(135deg,#10b981,#34d399)' },
          { icon: <CloseCircleOutlined />, label: '异常', value: abnormalCount, grad: 'linear-gradient(135deg,#ef4444,#f97316)' },
          { icon: <DashboardOutlined />, label: '平均健康分', value: avgScore, grad: 'linear-gradient(135deg,#f59e0b,#fbbf24)' },
        ].map((m) => (
          <div key={m.label} style={{ background: GLASS_BG, backdropFilter: 'blur(18px)', WebkitBackdropFilter: 'blur(18px)', border: GLASS_BORDER, borderRadius: 20, padding: '16px 20px', display: 'flex', alignItems: 'center', gap: 16, boxShadow: GLASS_SHADOW }}>
            <div style={{ width: 50, height: 50, borderRadius: 15, background: m.grad, color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 23, flex: 'none', boxShadow: '0 8px 18px rgba(0,0,0,0.12)' }}>{m.icon}</div>
            <div>
              <div style={{ fontSize: 12, color: TEXT_SUB }}>{m.label}</div>
              <div style={{ fontSize: 28, fontWeight: 800, color: TEXT_MAIN, marginTop: 2, fontFamily: 'Consolas,monospace' }}>{m.value}</div>
            </div>
          </div>
        ))}
      </div>

      {/* ===== 面板区 1：服务器状态 / 健康分布 / 健康分 ===== */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(280px,1fr))', gap: 16, marginBottom: 16 }}>
        <Panel title="服务器状态">
          {servers.length === 0 ? <EmptyTip text="暂无服务器，请先添加" /> : servers.map((s) => {
            const data = cache[s.id]
            const score = scores[s.id]?.score
            const details = scores[s.id]?.details || {}
            const meta = dbTypeMeta(s)
            const slow = parseCount(details.slow_sql?.value)
            const dead = parseCount(details.deadlocks?.value)
            return (
              <div key={s.id} style={{ background: 'rgba(255,255,255,0.6)', borderRadius: 14, padding: 14, marginBottom: 10, display: 'flex', alignItems: 'center', gap: 12 }}>
                <div style={{ width: 38, height: 38, borderRadius: 11, background: meta.grad, color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 16, fontWeight: 700, flex: 'none' }}>{meta.label}</div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 700, fontSize: 14, color: TEXT_MAIN, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{s.name}</div>
                  <div style={{ fontSize: 11, color: TEXT_SUB }}>{s.ssh_host || '本地'}:{s.ssh_port ?? 22} · {s.skip_db ? '仅系统' : (s.db_type || '').toUpperCase()}</div>
                  <div style={{ display: 'flex', gap: 10, fontSize: 10, fontFamily: 'Consolas,monospace', color: TEXT_SUB, marginTop: 3, alignItems: 'center', flexWrap: 'wrap' }}>
                    <span style={{ color: '#6366f1' }}>连接 {details.sessions?.value ?? '—'}</span>
                    <span>慢SQL <b onClick={() => openDetail(s, 'slow')} style={CLICK_STYLE}>{slow}</b></span>
                    <span>死锁 <b onClick={() => openDetail(s, 'dead')} style={CLICK_STYLE}>{dead}</b></span>
                  </div>
                </div>
                <div style={{ fontFamily: 'Consolas,monospace', fontSize: 22, fontWeight: 800, color: scoreColor(score), flex: 'none' }}>{score ?? '—'}</div>
              </div>
            )
          })}
        </Panel>

        <Panel title="健康分布">
          {servers.length === 0 ? <EmptyTip text="暂无服务器" /> : (
            <div style={{ display: 'flex', alignItems: 'center', gap: 18 }}>
              <div style={{ width: 118, height: 118, borderRadius: '50%', flex: 'none', position: 'relative', background: `conic-gradient(#10b981 0 ${pctOf(buckets.good)}%,#f59e0b ${pctOf(buckets.good)}% ${pctOf(buckets.good) + pctOf(buckets.warn)}%,#ef4444 ${pctOf(buckets.good) + pctOf(buckets.warn)}% ${pctOf(buckets.good) + pctOf(buckets.warn) + pctOf(buckets.bad)}%,#e5e7eb ${pctOf(buckets.good) + pctOf(buckets.warn) + pctOf(buckets.bad)}% 100%)` }}>
                <div style={{ position: 'absolute', inset: 14, borderRadius: '50%', background: 'rgba(255,255,255,0.88)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
                  <b style={{ fontSize: 26, fontFamily: 'Consolas,monospace', color: TEXT_MAIN }}>{avgScore}</b>
                  <span style={{ fontSize: 10, color: TEXT_SUB }}>平均分</span>
                </div>
              </div>
              <div style={{ flex: 1, fontSize: 12, color: '#64748b' }}>
                {[
                  { label: '🟢 良好 ≥80', n: buckets.good },
                  { label: '🟠 关注 60-79', n: buckets.warn },
                  { label: '🔴 异常 <60', n: buckets.bad },
                  { label: '⚪ 未采集', n: buckets.none },
                ].map((r) => (
                  <div key={r.label} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0' }}><span>{r.label}</span><b style={{ color: TEXT_MAIN, fontFamily: 'Consolas,monospace' }}>{r.n}</b></div>
                ))}
              </div>
            </div>
          )}
        </Panel>

        <Panel title="健康分">
          {loading && servers.length === 0 ? <EmptyTip text="加载中…" /> : servers.length === 0 ? <EmptyTip text="暂无服务器" /> : (
            <div style={{ display: 'flex', alignItems: 'flex-end', gap: 12, height: 150, paddingTop: 8 }}>
              {servers.map((s) => {
                const sc = scores[s.id]?.score
                const h = sc == null ? 8 : Math.max(10, sc * 1.3)
                return (
                  <div key={s.id} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'flex-end', height: '100%', minWidth: 0 }}>
                    <div style={{ fontSize: 11, fontFamily: 'Consolas,monospace', color: TEXT_MAIN, marginBottom: 4 }}>{sc ?? '—'}</div>
                    <div style={{ width: '62%', maxWidth: 36, height: h, background: `linear-gradient(180deg,${scoreColor(sc)},rgba(99,102,241,0.35))`, borderRadius: '8px 8px 3px 3px', boxShadow: '0 2px 8px rgba(99,102,241,0.2)' }} />
                    <div style={{ fontSize: 10, color: TEXT_SUB, marginTop: 6, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: '100%' }}>{s.name}</div>
                  </div>
                )
              })}
            </div>
          )}
        </Panel>
      </div>

      {/* ===== 面板区 2：数据库性能指标 / 实时操作记录 ===== */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(300px,1fr))', gap: 16 }}>
        <Panel title="数据库性能指标">
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 10 }}>
            {[
              { label: '总连接数', v: totalSessions, c: '#6366f1' },
              { label: '慢SQL', v: totalSlow, c: '#d97706' },
              { label: '死锁', v: totalDead, c: '#dc2626' },
            ].map((x) => (
              <div key={x.label} style={{ background: 'rgba(255,255,255,0.6)', borderRadius: 12, padding: 12, textAlign: 'center' }}>
                <div style={{ fontSize: 22, fontWeight: 800, fontFamily: 'Consolas,monospace', color: x.c }}>{x.v}</div>
                <div style={{ fontSize: 11, color: TEXT_SUB }}>{x.label}</div>
              </div>
            ))}
          </div>
          <div style={{ marginTop: 12, fontSize: 12, color: '#64748b', lineHeight: 2 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}><span>在线率</span><b style={{ color: '#059669' }}>{pctOf(onlineCount)}%</b></div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}><span>健康服务器</span><b style={{ color: '#059669' }}>{servers.length - buckets.none} 台</b></div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}><span>异常服务器</span><b style={{ color: '#dc2626' }}>{buckets.bad} 台</b></div>
          </div>
        </Panel>

        <Panel title="实时操作记录">
          {servers.length === 0 ? <EmptyTip text="暂无服务器" /> : servers.map((s) => {
            const data = cache[s.id]
            const score = scores[s.id]?.score
            return (
              <div key={s.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '9px 0', borderBottom: '1px solid rgba(148,163,184,0.2)' }}>
                <span className={dotClass(!!data, score)} />
                <span style={{ color: TEXT_MAIN, fontSize: 13, flex: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{s.name}</span>
                <span style={{ color: TEXT_SUB, fontSize: 11, fontFamily: 'Consolas,monospace' }}>{data?.timestamp || '暂无采集'}</span>
                <Space size={0}>
                  <Button size="small" type="text" icon={<EyeOutlined />} style={{ color: '#6366f1' }} onClick={() => navigate(`/server/${s.id}`)} />
                  <Button size="small" type="text" icon={<ThunderboltOutlined />} loading={collecting === s.id} style={{ color: '#6366f1' }} onClick={() => collect(s)} />
                  <Button size="small" type="text" icon={<DownloadOutlined />} style={{ color: '#6366f1' }} onClick={() => downloadFile(`/api/export/csv/${s.id}`, `${s.name}.csv`)} />
                </Space>
              </div>
            )
          })}
        </Panel>
      </div>

      {/* ===== 慢SQL / 死锁详情弹窗 ===== */}
      <Modal
        title={detail ? `${detail.server.name} · ${detail.type === 'slow' ? '慢SQL' : '死锁'} 详情` : ''}
        open={!!detail}
        onCancel={() => setDetail(null)}
        footer={null}
        width={700}
        maskClosable={false}
        destroyOnHidden
      >
        {detail && (
          detail.loading ? <Skeleton active paragraph={{ rows: 4 }} /> :
          detail.logs.length === 0 ? (
            <Empty description={detail.type === 'slow' ? '该服务器暂无慢SQL记录' : '该服务器暂无死锁记录'} />
          ) : (
            <div style={{ maxHeight: 420, overflow: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                <thead>
                  <tr>
                    {detail.type === 'slow' ? (
                      <><th style={thStyle}>SQL 语句</th><th style={thStyle}>耗时</th><th style={thStyle}>次数</th><th style={thStyle}>执行用户</th><th style={thStyle}>时间</th></>
                    ) : (
                      <><th style={thStyle}>描述</th><th style={thStyle}>次数</th><th style={thStyle}>时间</th></>
                    )}
                  </tr>
                </thead>
                <tbody>
                  {detail.logs.map((l, i) => (
                    <tr key={i}>
                      {detail.type === 'slow' ? (
                        <>
                          <td style={{ ...tdStyle, fontFamily: 'Consolas,monospace', fontSize: 12, maxWidth: 360, overflow: 'hidden', textOverflow: 'ellipsis' }}>{l.error_msg || l.exec_sql || '—'}</td>
                          <td style={tdStyle}>{l.cost_seconds != null ? `${l.cost_seconds}s` : '—'}</td>
                          <td style={tdStyle}>{l.occur_count ?? 1}</td>
                          <td style={tdStyle}>{l.exec_user || '—'}</td>
                          <td style={tdStyle}>{l.occur_time || '—'}</td>
                        </>
                      ) : (
                        <>
                          <td style={{ ...tdStyle, fontFamily: 'Consolas,monospace', fontSize: 12, maxWidth: 420, overflow: 'hidden', textOverflow: 'ellipsis' }}>{l.error_msg || '—'}</td>
                          <td style={tdStyle}>{l.occur_count ?? 1}</td>
                          <td style={tdStyle}>{l.occur_time || '—'}</td>
                        </>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        )}
      </Modal>
    </div>
  )
}
