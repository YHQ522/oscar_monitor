// 服务器详情页：健康评分 + OS 信息 + 分类查询 + 趋势图 + 应用状态
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useCacheStore } from '../store/cache'
import {
  Card, Descriptions, Tabs, Button, Space, Tag, Skeleton, Statistic, Row, Col, Empty,
} from 'antd'
import { App as AntApp } from 'antd'
import {
  ReloadOutlined, ThunderboltOutlined, DownloadOutlined, EditOutlined, ArrowLeftOutlined, FileTextOutlined,
} from '@ant-design/icons'
import { useNavigate, useParams } from 'react-router-dom'
import { api, downloadFile } from '../api/client'
import { fetchServerData } from '../hooks/useSSE'
import ServerStatusTag from '../components/ServerStatusTag'
import QueryTable from '../components/QueryTable'
import StoragePie from '../components/StoragePie'
import DiskUsage from '../components/DiskUsage'
import CpuPanel from '../components/CpuPanel'
import OsErrorsPanel from '../components/OsErrorsPanel'
import DbLogErrorsPanel from '../components/DbLogErrorsPanel'
import DbMemoryPanel from '../components/DbMemoryPanel'
import { LineChart, Line, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer, CartesianGrid } from 'recharts'
import type { CollectData, HealthScore, Server, TrendPoint, QuerySetMeta } from '../api/types'

const OS_LABELS: Record<string, string> = {
  memory: '内存使用情况',
  disk: '磁盘使用情况',
  cpu: 'CPU负载情况',
  install_path: '数据库安装路径',
  os_errors: '操作系统日志错误',
  db_log_errors: '数据库日志错误文件',
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

function scoreColor(score: number): string {
  if (score >= 80) return '#52c41a'
  if (score >= 60) return '#faad14'
  return '#f5222d'
}

export default function ServerDetailPage() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const { message } = AntApp.useApp()
  const [server, setServer] = useState<Server | null>(null)
  const [data, setData] = useState<CollectData | null>(null)
  const [health, setHealth] = useState<HealthScore | null>(null)
  const [trends, setTrends] = useState<TrendPoint[]>([])
  const [querySets, setQuerySets] = useState<Record<string, QuerySetMeta>>({})
  const [queryLabels, setQueryLabels] = useState<Record<string, string>>({})
  const [columnLabels, setColumnLabels] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(true)
  const [collecting, setCollecting] = useState(false)

  const loadAll = useCallback(async () => {
    try {
      const [s, meta] = await Promise.all([
        api.get<Server[]>('/api/servers').then((list) => list.find((x) => x.id === id)),
        api.get<{ query_sets: Record<string, Record<string, QuerySetMeta>>; query_labels: Record<string, string>; column_labels: Record<string, string> }>('/api/meta'),
      ])
      if (!s) {
        message.error('服务器不存在')
        navigate('/servers')
        return
      }
      setServer(s)
      setQuerySets(meta.query_sets[s.db_type] || {})
      setQueryLabels(meta.query_labels || {})
      setColumnLabels(meta.column_labels || {})
      const [cached, h] = await Promise.all([
        fetchServerData(id),
        api.get<HealthScore>(`/api/servers/${id}/health`).catch(() => null),
      ])
      if (cached) setData(cached)
      if (h) setHealth(h)
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [id, navigate])

  const loadTrends = useCallback(async () => {
    try {
      setTrends(await api.get<TrendPoint[]>(`/api/trends/${id}?hours=24`))
    } catch {
      /* ignore */
    }
  }, [id])

  // 订阅全局 SSE 缓存：采集推送自动刷新数据，避免 5s 轮询与 SSE 双通道冗余
  const sseData = useCacheStore((s) => s.data[id])

  useEffect(() => {
    loadAll()
    loadTrends()
  }, [loadAll, loadTrends, id])

  useEffect(() => {
    if (sseData) setData(sseData)
  }, [sseData])

  const collect = async (partial?: { categories: string[]; os_checks: string[] }) => {
    setCollecting(true)
    try {
      const result = partial
        ? await api.post<CollectData>(`/api/servers/${id}/collect-partial`, partial)
        : await api.post<CollectData>(`/api/servers/${id}/collect`)
      setData(result)
      loadTrends()
      api.get<HealthScore>(`/api/servers/${id}/health`).then((h) => setHealth(h)).catch(() => {})
      message.success('采集完成')
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setCollecting(false)
    }
  }

  const osTabs = useMemo(() => {
    if (!data?.os_info) return []
    return Object.entries(data.os_info).map(([key, result]) => {
      const label = OS_LABELS[key] || key
      // CPU：人性化面板（使用率仪表盘 + 概况 + 进程表）
      if (key === 'cpu') {
        return { key, label, children: <CpuPanel result={result} /> }
      }
      // 操作系统日志错误：人性化列表（时间 + 内容，错误码高亮；空态提示正常）
      if (key === 'os_errors') {
        return { key, label, children: <OsErrorsPanel result={result} /> }
      }
      // 数据库错误日志文件：级别筛选面板（默认只显示 ERROR/FATAL/WARNING，最新在前）
      if (key === 'db_log_errors') {
        return { key, label, children: <DbLogErrorsPanel result={result} /> }
      }
      return { key, label, children: <QueryTable result={result} title={label} columnLabels={columnLabels} /> }
    })
  }, [data, columnLabels])

  const dbTabs = useMemo(() => {
    if (!data?.db_queries) return []
    return Object.entries(data.db_queries).map(([cat, queries]) => ({
      key: cat,
      label: querySets[cat]?.label || cat,
      children: (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          {Object.entries(queries).map(([qname, result]) => {
            if (qname === 'db_memory') {
              return <DbMemoryPanel key={qname} result={result} title={queryLabels[qname] || '数据库内存'} />
            }
            return (
              <QueryTable
                key={qname}
                result={result}
                title={queryLabels[qname] || qname}
                columnLabels={columnLabels}
              />
            )
          })}
        </div>
      ),
    }))
  }, [data, querySets, queryLabels, columnLabels])

  if (loading) {
    return (
      <Card size="small">
        <Skeleton active paragraph={{ rows: 8 }} />
      </Card>
    )
  }
  if (!server) return null

  // 健康评分：使用后端 /health 统一评分（与首页一致，按已勾选采集项加权）
  const score = health?.score ?? null

  // 依据服务器采集配置决定显示哪些区块/指标（未配置的不显示）
  const osChecks = server.enabled_os_checks || []
  const cats = server.enabled_categories || []
  const skipDb = server.skip_db
  const hasApps = (server.apps || []).length > 0
  const hasStorage = !skipDb && cats.includes('storage')
  const hasDisk = osChecks.includes('disk')
  const hasCpu = osChecks.includes('cpu')
  const hasMem = osChecks.includes('memory')
  const hasPerf = !skipDb && cats.includes('performance')
  const detailEntries = Object.entries(health?.details || {})
  const detailSpan =
    detailEntries.length >= 4 ? 6 : detailEntries.length >= 3 ? 8 : detailEntries.length === 2 ? 12 : 24

  return (
    <div>
      <Space style={{ marginBottom: 16 }} wrap>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/')}>返回</Button>
        <h2 style={{ margin: 0, display: 'inline' }}>{server.name}</h2>
        <Tag>{server.skip_db ? '—' : server.db_type.toUpperCase()}</Tag>
        <ServerStatusTag data={data} />
        <Button icon={<ThunderboltOutlined />} loading={collecting} onClick={() => collect()}>全量采集</Button>
        <Button icon={<ReloadOutlined />} onClick={loadTrends}>刷新趋势</Button>
        <Button icon={<DownloadOutlined />} onClick={() => downloadFile(`/api/export/csv/${id}`, `${server.name}.csv`)}>导出 CSV</Button>
        {server.persist_enabled && (
          <Button icon={<FileTextOutlined />} onClick={() => navigate(`/server/${id}/log-history`)}>日志历史</Button>
        )}
        <Button icon={<EditOutlined />} onClick={() => navigate('/servers/add?edit=' + id)}>编辑</Button>
      </Space>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={8}>
          <Card title="服务器信息" size="small">
            <Descriptions column={1} size="small">
              <Descriptions.Item label="SSH">{server.ssh_host}:{server.ssh_port}</Descriptions.Item>
              <Descriptions.Item label="数据库">{server.skip_db ? '—（仅系统监控）' : `${server.db_host}:${server.db_port}`}</Descriptions.Item>
              <Descriptions.Item label="用户">{server.skip_db ? '—' : server.db_user}</Descriptions.Item>
              <Descriptions.Item label="库名">{server.skip_db ? '—' : server.db_name}</Descriptions.Item>
              <Descriptions.Item label="系统">{server.os_type}</Descriptions.Item>
              <Descriptions.Item label="采集时间">{data?.timestamp || '—'}</Descriptions.Item>
            </Descriptions>
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card title="健康概览" size="small">
            {score == null ? (
              <Empty description="暂无数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : (
              <div style={{ textAlign: 'center' }}>
                <Statistic
                  title="综合健康评分"
                  value={score}
                  suffix="/ 100"
                  valueStyle={{ color: scoreColor(score), fontSize: 36 }}
                />
                {detailEntries.length > 0 && (
                  <Row gutter={8} style={{ marginTop: 12 }}>
                    {detailEntries.map(([k, v]) => (
                      <Col span={detailSpan} key={k}>
                        <Statistic
                          title={DETAIL_LABELS[k] || k}
                          value={v.value}
                          valueStyle={{ fontSize: 18, color: v.status ? STATUS_COLORS[v.status] : undefined }}
                        />
                      </Col>
                    ))}
                  </Row>
                )}
              </div>
            )}
          </Card>
        </Col>
        {hasApps && (
          <Col xs={24} lg={8}>
            <Card title="应用状态" size="small">
              {!data?.apps?.length ? (
                <Empty description="暂无数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {data.apps.map((app) => (
                    <div key={app.name} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span>{app.name}</span>
                      <Tag color={app.running ? 'green' : 'red'}>{app.status}</Tag>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          </Col>
        )}
      </Row>

      <Card title="历史趋势" size="small" style={{ marginTop: 16 }}>
        {trends.length === 0 ? (
          <Empty description="暂无趋势数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : (
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={trends}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="ts" tick={{ fontSize: 10 }} />
              <YAxis yAxisId="pct" domain={[0, 100]} tick={{ fontSize: 10 }} />
              <YAxis yAxisId="num" orientation="right" tick={{ fontSize: 10 }} />
              <Tooltip />
              <Legend />
              {hasCpu && <Line yAxisId="pct" type="monotone" dataKey="cpu_pct" name="CPU%" stroke="#4f46e5" dot={false} />}
              {hasMem && <Line yAxisId="pct" type="monotone" dataKey="mem_pct" name="内存%" stroke="#f59e0b" dot={false} />}
              {hasPerf && <Line yAxisId="num" type="monotone" dataKey="sessions" name="连接数" stroke="#10b981" dot={false} />}
              {hasPerf && <Line yAxisId="num" type="monotone" dataKey="slow_sql_count" name="慢SQL" stroke="#ef4444" dot={false} />}
            </LineChart>
          </ResponsiveContainer>
        )}
      </Card>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        {hasStorage && (
          <Col xs={24} lg={12}>
            <Card title="存储空间分布" size="small">
              <StoragePie result={data?.db_queries?.storage?.schema_space} />
            </Card>
          </Col>
        )}
        {hasDisk && (
          <Col xs={24} lg={12}>
            <Card title="磁盘使用率" size="small">
              <DiskUsage result={data?.os_info?.disk} />
            </Card>
          </Col>
        )}
      </Row>

      <Card size="small" style={{ marginTop: 16 }}>
        <Tabs
          items={[
            ...(dbTabs.length ? [{ key: 'db', label: '数据库采集', children: <Tabs items={dbTabs} /> }] : []),
            ...(osTabs.length ? [{ key: 'os', label: '系统采集', children: <Tabs items={osTabs} /> }] : []),
          ]}
        />
      </Card>
    </div>
  )
}
