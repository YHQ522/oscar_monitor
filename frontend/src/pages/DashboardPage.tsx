// 全局监控首页：服务器卡片 + 实时指标 + 健康评分
import { useEffect, useState } from 'react'
import {
  Row, Col, Card, Button, Tag, Space, Statistic, Empty, Progress, Skeleton,
} from 'antd'
import { App as AntApp } from 'antd'
import {
  ReloadOutlined, EyeOutlined, DownloadOutlined, ThunderboltOutlined, PlusOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { api, downloadFile } from '../api/client'
import { useServerCache } from '../hooks/useSSE'
import type { Server, HealthScore } from '../api/types'
import { useAuth } from '../store/auth'

function scoreColor(score: number | null): string {
  if (score == null) return '#d9d9d9'
  if (score >= 80) return '#52c41a'
  if (score >= 60) return '#faad14'
  return '#f5222d'
}

// 健康指标标签：与后端 health.details 的 key 对应（只显示该服务器实际配置的采集项）
const DETAIL_LABELS: Record<string, string> = {
  cpu: 'CPU',
  memory: '内存',
  sessions: '连接数',
  slow_sql: '慢SQL',
  deadlocks: '死锁',
}

// 单项健康状态颜色（红黄绿）
const STATUS_COLORS: Record<string, string> = {
  healthy: '#52c41a',
  warning: '#faad14',
  danger: '#f5222d',
}

export default function DashboardPage() {
  const navigate = useNavigate()
  const user = useAuth((s) => s.user)
  const { message } = AntApp.useApp()
  const cache = useServerCache()
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

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20, flexWrap: 'wrap', gap: 8 }}>
        <h2 style={{ margin: 0 }}>全局监控</h2>
        <Space>
          <Tag style={{ marginRight: 4 }} color="green">≥80 良好</Tag>
          <Tag color="orange">60-79 关注</Tag>
          <Tag color="red">&lt;60 异常</Tag>
        </Space>
        <Space>
          {canEdit && (
            <Button icon={<PlusOutlined />} onClick={() => navigate('/servers/add')}>
              添加服务器
            </Button>
          )}
          <Button icon={<ReloadOutlined />} onClick={collectAll} loading={loading} disabled={!servers.length}>
            全部采集
          </Button>
        </Space>
      </div>

      {servers.length > 0 && (
        <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
          <Col xs={12} sm={6}>
            <Card size="small"><Statistic title="服务器总数" value={servers.length} /></Card>
          </Col>
          <Col xs={12} sm={6}>
            <Card size="small"><Statistic title="在线" value={onlineCount} valueStyle={{ color: '#52c41a' }} /></Card>
          </Col>
          <Col xs={12} sm={6}>
            <Card size="small">
              <Statistic title="异常(&lt;60)" value={abnormalCount} valueStyle={{ color: abnormalCount ? '#f5222d' : undefined }} />
            </Card>
          </Col>
          <Col xs={12} sm={6}>
            <Card size="small"><Statistic title="平均健康分" value={avgScore} suffix={avgScore !== '—' ? '/100' : ''} /></Card>
          </Col>
        </Row>
      )}

      {error && <Tag color="error" style={{ marginBottom: 16 }}>{error}</Tag>}

      {loading && servers.length === 0 ? (
        <Card size="small"><Skeleton active paragraph={{ rows: 6 }} /></Card>
      ) : servers.length === 0 ? (
        <Empty description="暂无服务器，请先在服务管理中配置">
          {canEdit && (
            <Button type="primary" onClick={() => navigate('/servers/add')}>添加服务器</Button>
          )}
        </Empty>
      ) : (
        <Row gutter={[16, 16]}>
          {servers.map((server) => {
            const data = cache[server.id]
            const score = scores[server.id]?.score
            const runningApps = data?.apps?.filter((a) => a.running).length ?? 0
            const hasApps = (server.apps || []).length > 0
            // 指标区由后端 health.details 驱动：只显示该服务器实际配置的采集项
            const metricCols = [
              ...Object.entries(scores[server.id]?.details || {}).map(([k, v]) => ({
                key: k,
                title: DETAIL_LABELS[k] || k,
                value: v.value,
                color: v.status ? STATUS_COLORS[v.status] : undefined,
              })),
              ...(hasApps ? [{ key: 'apps', title: '运行应用', value: data ? `${runningApps}/${data.apps?.length ?? 0}` : '—', color: undefined }] : []),
              ...(!server.skip_db ? [{ key: 'type', title: '类型', value: (server.db_type || 'oscar').toUpperCase(), color: undefined }] : []),
            ]
            const metricSpan = metricCols.length >= 4 ? 6 : metricCols.length >= 3 ? 8 : 12

            return (
              <Col xs={24} sm={12} lg={8} xl={6} key={server.id}>
                <Card
                  size="small"
                  title={
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span>{server.name}</span>
                      {data ? (
                        <Tag color="green" style={{ margin: 0 }}>在线</Tag>
                      ) : (
                        <Tag color="default" style={{ margin: 0 }}>未采集</Tag>
                      )}
                    </div>
                  }
                  extra={
                    <Progress
                      type="circle"
                      size={42}
                      percent={score ?? 0}
                      strokeColor={scoreColor(score)}
                      format={() => (score == null ? '—' : score)}
                    />
                  }
                  actions={[
                    <Button key="view" type="text" icon={<EyeOutlined />} onClick={() => navigate(`/server/${server.id}`)}>
                      详情
                    </Button>,
                    <Button
                      key="collect"
                      type="text"
                      icon={<ThunderboltOutlined />}
                      loading={collecting === server.id}
                      onClick={() => collect(server)}
                    >
                      采集
                    </Button>,
                    <Button
                      key="export"
                      type="text"
                      icon={<DownloadOutlined />}
                      onClick={() => downloadFile(`/api/export/csv/${server.id}`, `${server.name}.csv`)}
                    >
                      导出
                    </Button>,
                  ]}
                >
                  <div style={{ fontSize: 12, color: '#8a94a6', marginBottom: 10 }}>
                    采集时间：{data?.timestamp || '—'}
                  </div>
                  {metricCols.length > 0 && (
                    <Row gutter={[8, 8]}>
                      {metricCols.map((m) => (
                        <Col span={metricSpan} key={m.key}>
                          <Statistic title={m.title} value={m.value} valueStyle={{ fontSize: 18, color: m.color || undefined }} />
                        </Col>
                      ))}
                    </Row>
                  )}
                </Card>
              </Col>
            )
          })}
        </Row>
      )}
    </div>
  )
}
