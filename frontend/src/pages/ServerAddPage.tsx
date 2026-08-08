// 添加/编辑服务器
import { useEffect, useRef, useState } from 'react'
import {
  Form, Input, InputNumber, Select, Button, Card, Row, Col, Space, Checkbox, Divider, Steps, Switch, Tag, Modal, Descriptions, Radio, Alert,
} from 'antd'
import { App as AntApp } from 'antd'
import { ApiOutlined } from '@ant-design/icons'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../api/client'
import type { Server, QuerySetMeta } from '../api/types'

interface Meta {
  db_types: Record<string, string>
  query_sets: Record<string, Record<string, QuerySetMeta>>
  os_check_labels: Record<string, string>
  os_checks: string[]
  log_enabled?: boolean
}

// 依赖数据库的系统检查项：仅系统模式（skip_db）下应排除
const DB_RELATED_OS_CHECKS = ['install_path', 'db_log_errors']

// 分步向导：每一步对应的表单字段（用于分步校验）
// 数据库类型属于「数据库连接」步骤（第 3 步），与连接参数联动；仅系统模式下该步骤整体跳过
const STEP_FIELDS: string[][] = [
  ['name', 'os_type', 'ssh_host', 'ssh_port', 'ssh_user', 'ssh_pass', 'auto_refresh'],
  ['enabled_categories', 'enabled_os_checks'],
  ['db_type', 'db_host', 'db_port', 'db_user', 'db_pass', 'db_name', 'isql_cmd'],
  ['in_control', 'svc_name', 'svc_mgr', 'svc_start_cmd', 'svc_stop_cmd', 'persist_enabled'],
  [],
]

export default function ServerAddPage() {
  const navigate = useNavigate()
  const { message } = AntApp.useApp()
  const [params] = useSearchParams()
  const editId = params.get('edit')
  const [form] = Form.useForm()
  const [meta, setMeta] = useState<Meta | null>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [apps, setApps] = useState<any[]>([])
  const [dbType, setDbType] = useState('oscar')
  const [collectMode, setCollectMode] = useState<'os' | 'both' | 'db'>('both')
  // 系统级日志持久化开关（meta 返回；未开启时禁用服务器级开关并提示）
  const [logEnabled, setLogEnabled] = useState(true)
  // 防 StrictMode 双执行导致重复弹出提示
  const warnedRef = useRef(false)
  const [currentStep, setCurrentStep] = useState(0)
  const [saving, setSaving] = useState(false)
  const [testLoading, setTestLoading] = useState(false)
  const [sshTestLoading, setSshTestLoading] = useState(false)
  const [testOpen, setTestOpen] = useState(false)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [testResult, setTestResult] = useState<any>(null)

  useEffect(() => {
    api.get<Meta>('/api/meta')
      .then((m) => {
        setMeta(m)
        // 系统级日志持久化开关：未开启时禁用服务器级开关并直接提示
        setLogEnabled(m.log_enabled !== false)
        if (m.log_enabled === false && !warnedRef.current) {
          warnedRef.current = true
          message.warning('全局日志持久化未开启，服务器「日志持久化」开关已禁用，请先在系统配置中开启')
        }
        // 非编辑模式：初始化采集项为默认「系统+数据库」（后端不再自动填充空列表）
        if (!editId) {
          const allCats = Object.keys(m.query_sets['oscar'] || {})
          form.setFieldsValue({ enabled_categories: allCats, enabled_os_checks: m.os_checks })
        }
      })
      .catch((e) => message.error(e.message))
  }, [editId, form])

  useEffect(() => {
    if (editId) {
      api.get<Server[]>('/api/servers')
        .then((list) => list.find((s) => s.id === editId))
        .then((server) => {
          if (!server) return
          form.setFieldsValue(server)
          setApps(server.apps || [])
          setDbType(server.db_type)
          // 根据已有配置推断采集模式
          const cats = server.enabled_categories || []
          const os = server.enabled_os_checks || []
          if (server.skip_db || (cats.length === 0 && os.length > 0)) setCollectMode('os')
          else if (cats.length > 0 && os.length === 0) setCollectMode('db')
          else setCollectMode('both')
        })
    }
  }, [editId, form])

  const onDbTypeChange = (value: string) => {
    setDbType(value)
    const qs = meta?.query_sets[value]
    // 各类型默认连接参数
    const defaults: Record<string, { port: number; user: string; db: string; cli: string }> = {
      oscar: { port: 2003, user: 'SYSDBA', db: 'OSRDB', cli: 'isql' },
      mysql: { port: 3306, user: 'root', db: 'mysql', cli: 'mysql' },
      postgresql: { port: 5432, user: 'postgres', db: 'postgres', cli: 'psql' },
      oracle: { port: 1521, user: 'system', db: 'ORCL', cli: 'sqlplus' },
    }
    const d = defaults[value] || defaults.oscar
    if (qs) {
      // 切换类型时尊重当前采集模式：仅系统保持数据库类别为空，且排除依赖数据库的系统项
      const cats = collectMode === 'os' ? [] : Object.keys(qs)
      let os = meta.os_checks
      if (collectMode === 'db') os = []
      else if (collectMode === 'os') os = os.filter((k) => !DB_RELATED_OS_CHECKS.includes(k))
      form.setFieldsValue({
        enabled_categories: cats,
        enabled_os_checks: os,
        db_port: d.port,
        db_user: d.user,
        db_name: d.db,
        isql_cmd: d.cli,
      })
    }
  }

  const applyCollectMode = (mode: 'os' | 'both' | 'db') => {
    setCollectMode(mode)
    const allCats = Object.keys(meta?.query_sets[dbType] || {})
    const allOs = meta?.os_checks || []
    if (mode === 'os') {
      // 仅系统：不采集数据库，并排除依赖数据库的系统项（安装路径/数据库日志）
      const pureOs = allOs.filter((k) => !DB_RELATED_OS_CHECKS.includes(k))
      form.setFieldsValue({ enabled_categories: [], enabled_os_checks: pureOs })
    } else if (mode === 'db') {
      form.setFieldsValue({ enabled_categories: allCats, enabled_os_checks: [] })
    } else {
      form.setFieldsValue({ enabled_categories: allCats, enabled_os_checks: allOs })
    }
    // 模式切换后按新规则重新校验（清除旧错误 / 校验新必填）
    form.validateFields().catch(() => { })
  }

  const testConnection = async () => {
    try {
      const values = await form.validateFields()
      setTestLoading(true)
      const result = await api.post<{ ssh: { ok: boolean; msg: string }; db: { ok: boolean; msg: string; version?: string[] } }>(
        '/api/test-connection',
        { ...values, skip_db: collectMode === 'os' },
      )
      setTestResult(result)
      setTestOpen(true)
      if (result.ssh) {
        result.ssh.ok ? message.success(`SSH: ${result.ssh.msg}`) : message.error(`SSH: ${result.ssh.msg}`)
      }
      if (result.db) {
        result.db.ok ? message.success(`数据库: ${result.db.msg}`) : message.error(`数据库: ${result.db.msg}`)
      }
    } catch (e) {
      message.error((e as Error).message || '请先填写完整配置')
    } finally {
      setTestLoading(false)
    }
  }

  // 第 1 步：仅测试 SSH 连接（skip_db=true 跳过数据库）
  const testSsh = async () => {
    try {
      const values = await form.validateFields(['ssh_host', 'ssh_port', 'ssh_user', 'ssh_pass', 'os_type'])
      setSshTestLoading(true)
      const result = await api.post<{ ssh: { ok: boolean; msg: string } }>(
        '/api/test-connection',
        { ...values, skip_db: true },
      )
      if (result.ssh) {
        result.ssh.ok ? message.success(`SSH：${result.ssh.msg}`) : message.error(`SSH：${result.ssh.msg}`)
      }
    } catch (e) {
      message.error((e as Error).message || '请先填写 SSH 配置')
    } finally {
      setSshTestLoading(false)
    }
  }

  const next = async () => {
    // 仅系统模式：数据库连接步骤无需填写，直接跳过
    if (currentStep === 2 && collectMode === 'os') {
      setCurrentStep(3)
      return
    }
    try {
      await form.validateFields(STEP_FIELDS[currentStep])
      setCurrentStep(currentStep + 1)
    } catch (err) {
      // 校验失败：光标自动跳到第一个未填写的必填字段
      focusFirstError(err)
    }
  }

  const onSubmit = async () => {
    setSaving(true)
    try {
      const values = await form.validateFields()
      const payload = { ...values, apps, skip_db: collectMode === 'os' }
      // 系统未开启日志持久化时，强制关闭服务器级开关（避免确认页与实际不符）
      if (!logEnabled) payload.persist_enabled = false
      // 提交前连接校验：SSH 不通 → 阻止保存；DB 不通 → 警告但仍保存
      // （编辑模式密码留空=不修改，无法校验则跳过）
      const sshPassProvided = editId ? !!values.ssh_pass : true
      const dbPassProvided = editId ? !!values.db_pass : true
      if (sshPassProvided || dbPassProvided) {
        const test = await api
          .post<{ ssh?: { ok: boolean; msg: string }; db?: { ok: boolean; msg: string } }>('/api/test-connection', payload)
          .catch(() => null)
        if (test) {
          if (test.ssh && !test.ssh.ok && sshPassProvided) {
            message.error(`SSH 连接校验未通过：${test.ssh.msg}（已阻止保存）`)
            setSaving(false)
            return
          }
          if (test.db && !test.db.ok && !payload.skip_db && dbPassProvided) {
            message.warning(`数据库连接校验未通过：${test.db.msg}（仍将保存配置）`)
          }
        }
      }
      if (editId) {
        await api.put(`/api/servers/${editId}`, payload)
        message.success('保存成功')
      } else {
        await api.post('/api/servers', payload)
        message.success('添加成功')
      }
      navigate('/servers')
    } catch (e) {
      // 校验失败：光标自动跳到第一个未填写的必填字段
      focusFirstError(e)
      message.error('请先填写必填项')
    } finally {
      setSaving(false)
    }
  }

  const addApp = () => {
    setApps([...apps, { name: '', port: 0, svc_name: '', svc_mgr: 'systemctl', in_control: true, group: '其他应用' }])
  }

  const updateApp = (index: number, field: string, value: unknown) => {
    const next = [...apps]
    next[index] = { ...next[index], [field]: value }
    setApps(next)
  }

  const removeApp = (index: number) => {
    setApps(apps.filter((_, i) => i !== index))
  }

  const querySets = meta?.query_sets[dbType] || {}
  const osCheckLabels = meta?.os_check_labels || {}

  // 响应式监听表单值（确认页展示用）：
  // 避免在 render 阶段调用 form.getFieldValue()——那既非响应式（确认页显示过期数据），
  // 又会在 Form 挂载前触发 rc-field-form 的 useForm 未连接警告
  const wName = Form.useWatch('name', form)
  const wOsType = Form.useWatch('os_type', form)
  const wDbType = Form.useWatch('db_type', form)
  const wSshHost = Form.useWatch('ssh_host', form)
  const wSshPort = Form.useWatch('ssh_port', form)
  const wDbHost = Form.useWatch('db_host', form)
  const wDbPort = Form.useWatch('db_port', form)
  const wInControl = Form.useWatch('in_control', form)
  const wPersist = Form.useWatch('persist_enabled', form)
  const wCategories = Form.useWatch('enabled_categories', form)
  const wOsChecks = Form.useWatch('enabled_os_checks', form)
  const OS_LABELS: Record<string, string> = { linux: 'Linux', windows: 'Windows' }

  // 条件必填校验：cond 为 true 时必填，否则放行（用于采集模式/开关联动的字段）
  const requireIf = (cond: boolean, message = '必填') => ({
    validator: (_: unknown, value: unknown) =>
      cond && (value === undefined || value === null || value === '')
        ? Promise.reject(new Error(message))
        : Promise.resolve(),
  })
  // SSH 本地判断：为空 / 127.0.0.1 / localhost 视为本地（无需 SSH 密码）
  const isLocalSsh = !wSshHost || wSshHost === '127.0.0.1' || wSshHost === 'localhost'

  // 校验失败时，光标自动跳到第一个未填写的必填字段
  const focusFirstError = (err: unknown) => {
    const errorFields = (err as { errorFields?: { name: (string | number)[] }[] }).errorFields
    if (!errorFields || errorFields.length === 0) return
    const name = String(errorFields[0].name[0])
    const el = document.getElementById(name)
    if (!el) return
    // Select/Checkbox.Group 等容器取其内部可聚焦控件
    const focusable = (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement || el.tagName === 'BUTTON')
      ? el
      : (el.querySelector('input, textarea') || el)
    if (focusable && typeof (focusable as HTMLElement).focus === 'function') {
      ;(focusable as HTMLElement).focus()
    }
    el.scrollIntoView({ block: 'center', behavior: 'smooth' })
  }

  // 服务管理器监听：联动显示是否需要填写自定义命令
  const svcMgr = Form.useWatch('svc_mgr', form)
  const svcMgrHelp = (() => {
    switch (svcMgr) {
      case 'systemctl': return '通过 systemctl start/stop <服务名> 管理（Linux 主流）'
      case 'service': return '通过 service <服务名> start/stop 管理（传统 SysVinit）'
      case 'script': return '使用自研脚本，需在下方填写启动/停止命令'
      case '/etc/init.d': return '通过 /etc/init.d/<服务名> start/stop 管理'
      default: return '选择数据库服务的托管方式'
    }
  })()
  const svcMgrTitle = svcMgr === 'script' ? '自定义脚本' : svcMgr || 'systemctl'

  return (
    <Card title={editId ? '编辑服务器' : '添加服务器'} style={{ overflowX: 'hidden' }}>
      <Form
        form={form}
        layout="vertical"
        onValuesChange={(changed) => {
          // 服务管理器/管控开关/SSH 主机变化时，重新校验联动必填字段
          if ('svc_mgr' in changed) form.validateFields(['svc_start_cmd', 'svc_stop_cmd']).catch(() => { })
          if ('in_control' in changed) form.validateFields(['svc_name']).catch(() => { })
          if ('ssh_host' in changed) form.validateFields(['ssh_pass']).catch(() => { })
        }}
        initialValues={{
        ssh_port: 22,
        ssh_user: 'root',
        db_port: 2003,
        db_user: 'SYSDBA',
        db_name: 'OSRDB',
        db_type: 'oscar',
        os_type: 'linux',
        isql_cmd: 'isql',
        svc_mgr: 'systemctl',
        auto_refresh: 0,
      }}>
        <Steps
          current={currentStep}
          onChange={(c) => setCurrentStep(c)}
          items={[
            { title: '基本信息', description: '名称 / SSH' },
            { title: '采集配置', description: '模式与范围' },
            { title: '数据库连接', description: collectMode === 'os' ? '无需填写' : '连接参数' },
            { title: '管控配置', description: '服务 / 应用' },
            { title: '确认', description: '提交' },
          ]}
        />
        <div style={{ marginTop: 24 }}>
          <div style={{ display: currentStep === 0 ? 'block' : 'none' }}>
            <Row gutter={[16, 8]}>
              <Col xs={24} sm={12} md={8}>
                <Form.Item name="name" label="服务器名称" rules={[{ required: true, message: '必填' }]}>
                  <Input placeholder="例如：生产库-01" />
                </Form.Item>
              </Col>
              <Col xs={24} sm={12} md={8}>
                <Form.Item name="os_type" label="操作系统">
                  <Select
                    options={[{ value: 'linux', label: 'Linux' }, { value: 'windows', label: 'Windows' }]}
                    onChange={(v: string) => {
                      // 选择操作系统时自动补全 SSH 默认用户：
                      // 当前值为空或仍是另一系统的默认值（自动补全残留）→ 切换为新系统默认；
                      // 用户手动输入过 → 保留
                      const def: Record<string, string> = { linux: 'root', windows: 'Administrator' }
                      const cur = form.getFieldValue('ssh_user')
                      const other = v === 'windows' ? 'root' : 'Administrator'
                      if (!cur || cur === other) {
                        form.setFieldsValue({ ssh_user: def[v] })
                      }
                    }}
                  />
                </Form.Item>
              </Col>
              <Col xs={24} sm={12} md={8}>
                <Form.Item name="ssh_host" label="SSH 主机" rules={[{ required: true, message: '必填' }]}>
                  <Input placeholder="127.0.0.1 表示本地" />
                </Form.Item>
              </Col>
              <Col xs={8} sm={6} md={4}>
                <Form.Item name="ssh_port" label="SSH 端口" rules={[{ required: true, message: '必填' }]}>
                  <InputNumber min={1} max={65535} style={{ width: '100%' }} />
                </Form.Item>
              </Col>
              <Col xs={8} sm={6} md={6}>
                <Form.Item name="ssh_user" label="SSH 用户" rules={[{ required: true, message: '必填' }]}>
                  <Input />
                </Form.Item>
              </Col>
              <Col xs={8} sm={6} md={6}>
                <Form.Item
                  name="ssh_pass"
                  label="SSH 密码"
                  extra={editId ? '留空表示不修改' : (isLocalSsh ? '本地无需密码' : undefined)}
                  rules={[requireIf(!editId && !isLocalSsh)]}
                  required={!editId && !isLocalSsh}
                >
                  <Input.Password placeholder={editId ? '（已保存）' : ''} />
                </Form.Item>
              </Col>
              <Col xs={24} sm={12} md={8}>
                <Form.Item name="auto_refresh" label="自动刷新间隔(秒, 0=不自动)">
                  <InputNumber min={0} max={3600} style={{ width: '100%' }} />
                </Form.Item>
              </Col>
            </Row>
            <Space style={{ marginTop: 8 }}>
              <Button icon={<ApiOutlined />} onClick={testSsh} loading={sshTestLoading}>
                测试 SSH 连接
              </Button>
            </Space>
          </div>

          <div style={{ display: currentStep === 1 ? 'block' : 'none' }}>
            <>
              <Form.Item label="采集模式" style={{ marginBottom: 16 }}>
                <Radio.Group value={collectMode} onChange={(e) => applyCollectMode(e.target.value)}>
                  <Radio.Button value="os">🔧 仅系统（不连数据库）</Radio.Button>
                  <Radio.Button value="both">⚙️ 系统 + 数据库</Radio.Button>
                  <Radio.Button value="db">🗄️ 仅数据库</Radio.Button>
                </Radio.Group>
                <div style={{ marginTop: 8, color: '#888' }}>
                  {collectMode === 'os'
                    ? '仅采集 CPU / 内存 / 磁盘 / 进程等系统指标，无需填写数据库连接信息。'
                    : collectMode === 'db'
                      ? '仅采集数据库类别指标，需配置数据库连接信息。'
                      : '同时采集系统指标与数据库指标。'}
                </div>
              </Form.Item>
              <Row gutter={[24, 8]}>
                <Col xs={24} md={12}>
                  <Form.Item
                    name="enabled_categories"
                    label="数据库采集类别"
                    required={collectMode !== 'os'}
                    rules={[{
                      validator: (_, value: string[]) =>
                        collectMode !== 'os' && !(value && value.length > 0)
                          ? Promise.reject(new Error('至少选择一项'))
                          : Promise.resolve(),
                    }]}
                  >
                    <Checkbox.Group
                      options={Object.entries(querySets).map(([k, v]) => ({ value: k, label: v.label }))}
                      style={{ display: 'flex', flexDirection: 'column', gap: 6 }}
                      disabled={collectMode === 'os'}
                    />
                  </Form.Item>
                </Col>
                <Col xs={24} md={12}>
                  <Form.Item
                    name="enabled_os_checks"
                    label="系统采集项"
                    required={collectMode !== 'db'}
                    rules={[{
                      validator: (_, value: string[]) =>
                        collectMode !== 'db' && !(value && value.length > 0)
                          ? Promise.reject(new Error('至少选择一项'))
                          : Promise.resolve(),
                    }]}
                  >
                    <Checkbox.Group
                      options={(meta?.os_checks || []).map((k) => ({
                        value: k,
                        label: DB_RELATED_OS_CHECKS.includes(k)
                          ? `${osCheckLabels[k] || k}（依赖数据库）`
                          : osCheckLabels[k] || k,
                      }))}
                      style={{ display: 'flex', flexDirection: 'column', gap: 6 }}
                      disabled={collectMode === 'db'}
                    />
                  </Form.Item>
                </Col>
              </Row>
            </>
          </div>

          <div style={{ display: currentStep === 2 ? 'block' : 'none' }}>
            <>
              {collectMode === 'os' && (
                <Alert type="info" showIcon message="已选择「仅系统」采集模式，无需填写数据库连接信息，可直接下一步。" style={{ marginBottom: 16 }} />
              )}
              <Row gutter={[16, 8]}>
                <Col xs={24} sm={12} md={8}>
                  <Form.Item name="db_type" label="数据库类型">
                    <Select
                      options={Object.entries(meta?.db_types || {}).map(([v, l]) => ({ value: v, label: l }))}
                      onChange={onDbTypeChange}
                      disabled={collectMode === 'os'}
                    />
                  </Form.Item>
                </Col>
                <Col xs={24} sm={12} md={8}>
                  <Form.Item name="db_host" label="数据库主机" rules={[requireIf(collectMode !== 'os')]} required={collectMode !== 'os'}>
                    <Input disabled={collectMode === 'os'} />
                  </Form.Item>
                </Col>
                <Col xs={8} sm={6} md={4}>
                  <Form.Item name="db_port" label="数据库端口" rules={[requireIf(collectMode !== 'os')]} required={collectMode !== 'os'}>
                    <InputNumber min={1} max={65535} style={{ width: '100%' }} disabled={collectMode === 'os'} />
                  </Form.Item>
                </Col>
                <Col xs={8} sm={6} md={6}>
                  <Form.Item name="db_user" label="数据库用户" rules={[requireIf(collectMode !== 'os')]} required={collectMode !== 'os'}>
                    <Input disabled={collectMode === 'os'} />
                  </Form.Item>
                </Col>
                <Col xs={8} sm={6} md={6}>
                  <Form.Item
                    name="db_pass"
                    label="数据库密码"
                    extra={editId ? '留空表示不修改' : undefined}
                    rules={[requireIf(!editId && collectMode !== 'os')]}
                    required={!editId && collectMode !== 'os'}
                  >
                    <Input.Password placeholder={editId ? '（已保存）' : ''} disabled={collectMode === 'os'} />
                  </Form.Item>
                </Col>
                <Col xs={24} sm={12} md={8}>
                  <Form.Item name="db_name" label="数据库名" rules={[requireIf(collectMode !== 'os')]} required={collectMode !== 'os'}>
                    <Input disabled={collectMode === 'os'} />
                  </Form.Item>
                </Col>
                <Col xs={24} sm={12} md={8}>
                  <Form.Item name="isql_cmd" label="CLI 命令" rules={[requireIf(collectMode !== 'os')]} required={collectMode !== 'os'}>
                    <Input placeholder="isql / mysql / psql / sqlplus" disabled={collectMode === 'os'} />
                  </Form.Item>
                </Col>
              </Row>
              {collectMode !== 'os' && (
                <Space style={{ marginTop: 8 }}>
                  <Button onClick={testConnection} loading={testLoading}>测试连接</Button>
                </Space>
              )}
            </>
          </div>

          <div style={{ display: currentStep === 3 ? 'block' : 'none' }}>
            <>
              <Alert
                type="info"
                showIcon
                style={{ marginBottom: 16 }}
                message="管控操作通过 SSH 在服务器上执行。数据库由 systemd 等托管时，选对应服务管理器即可自动启停，无需填写命令；使用自研脚本时选「自定义脚本」并填写下方命令。"
              />
              <Row gutter={[16, 8]}>
                <Col xs={24} sm={12} md={8}>
                  <Form.Item name="in_control" label="启用管控" valuePropName="checked" extra="开启后可在「启停管控」页执行 启动/停止/重启">
                    <Switch />
                  </Form.Item>
                </Col>
                <Col xs={24} sm={12} md={8}>
                  <Form.Item name="svc_name" label="服务名" extra="数据库服务名称（如 oscardb_OSRDBd）" rules={[requireIf(!!wInControl)]} required={!!wInControl}>
                    <Input placeholder="oscardb_OSRDBd" />
                  </Form.Item>
                </Col>
                <Col xs={24} sm={12} md={8}>
                  <Form.Item name="svc_mgr" label="服务管理器" extra={svcMgrHelp}>
                    <Select
                      options={[
                        { value: 'systemctl', label: 'systemctl（systemd）' },
                        { value: 'service', label: 'service（SysVinit）' },
                        { value: 'script', label: '自定义脚本' },
                        { value: '/etc/init.d', label: '/etc/init.d 脚本' },
                      ]}
                    />
                  </Form.Item>
                </Col>
              </Row>
              <Row gutter={[16, 8]}>
                <Col span={24} style={{ display: svcMgr === 'script' ? 'block' : 'none' }}>
                  <Alert type="warning" showIcon style={{ marginBottom: 8 }} message="已选择「自定义脚本」模式，请填写下方启动与停止命令（通过 SSH 在服务器上执行的 Shell 命令）。" />
                </Col>
                <Col xs={24} md={12} style={{ display: svcMgr === 'script' ? 'block' : 'none' }}>
                  <Form.Item name="svc_start_cmd" label="启动命令" extra="点击「启动」时在服务器上执行的 Shell 命令" rules={[requireIf(svcMgr === 'script')]} required={svcMgr === 'script'}>
                    <Input.TextArea rows={2} placeholder="例如：su - oscar -c '/opt/oscardb/bin/oscar start'" />
                  </Form.Item>
                </Col>
                <Col xs={24} md={12} style={{ display: svcMgr === 'script' ? 'block' : 'none' }}>
                  <Form.Item name="svc_stop_cmd" label="停止命令" extra="点击「停止」时在服务器上执行的 Shell 命令" rules={[requireIf(svcMgr === 'script')]} required={svcMgr === 'script'}>
                    <Input.TextArea rows={2} placeholder="例如：su - oscar -c '/opt/oscardb/bin/oscar stop'" />
                  </Form.Item>
                </Col>
                <Col xs={24} md={12} style={{ display: svcMgr === 'script' ? 'none' : 'block' }}>
                  <div style={{ background: '#f5f5f5', borderRadius: 6, padding: '8px 12px', color: '#666', fontSize: 13, minHeight: 96, display: 'flex', alignItems: 'center' }}>
                    <span>
                      当前「{svcMgrTitle}」会自动执行数据库的启动/停止，<b>无需填写命令</b>。
                      <br />
                      仅当选择「自定义脚本」时才需要手动填写启动/停止命令。
                    </span>
                  </div>
                </Col>
                <Col span={24}>
                  {!logEnabled && (
                    <Alert
                      type="warning"
                      showIcon
                      style={{ marginBottom: 8 }}
                      message="全局日志持久化未开启"
                      description="请先在「系统配置」中开启日志持久化并配置日志库，否则该服务器无法写入日志。"
                    />
                  )}
                  <Form.Item
                    name="persist_enabled"
                    label="启用日志持久化（需全局配置日志库）"
                    valuePropName="checked"
                    extra={logEnabled ? '采集到的数据库错误与慢 SQL 写入全局日志库' : '需先在系统配置中开启日志持久化'}
                  >
                    <Switch disabled={!logEnabled} />
                  </Form.Item>
                </Col>
              </Row>
              <Divider orientation="left">应用监控</Divider>
              <div>
                {apps.map((app, i) => (
                  <Row gutter={[12, 8]} key={i} style={{ marginBottom: 8 }}>
                    <Col xs={10} sm={4}><Input placeholder="应用名" value={app.name as string} onChange={(e) => updateApp(i, 'name', e.target.value)} /></Col>
                    <Col xs={7} sm={3}><InputNumber placeholder="端口" min={0} value={app.port as number} onChange={(v) => updateApp(i, 'port', v)} style={{ width: '100%' }} /></Col>
                    <Col xs={7} sm={4}><Input placeholder="服务名" value={app.svc_name as string} onChange={(e) => updateApp(i, 'svc_name', e.target.value)} /></Col>
                    <Col xs={10} sm={3}>
                      <Select
                        value={app.svc_mgr as string}
                        options={[{ value: 'systemctl', label: 'systemctl' }, { value: 'service', label: 'service' }]}
                        onChange={(v) => updateApp(i, 'svc_mgr', v)}
                        style={{ width: '100%' }}
                      />
                    </Col>
                    <Col xs={10} sm={4}><Input placeholder="分组" value={app.group as string} onChange={(e) => updateApp(i, 'group', e.target.value)} /></Col>
                    <Col xs={5} sm={2}><Checkbox checked={app.in_control as boolean} onChange={(e) => updateApp(i, 'in_control', e.target.checked)}>管控</Checkbox></Col>
                    <Col xs={5} sm={2}><Button danger size="small" onClick={() => removeApp(i)}>删除</Button></Col>
                    {app.name && <Tag style={{ marginLeft: 8 }}>{app.name}</Tag>}
                  </Row>
                ))}
                <Button type="dashed" onClick={addApp} block>+ 添加应用</Button>
              </div>
            </>
          </div>

          <div style={{ display: currentStep === 4 ? 'block' : 'none' }}>
            <Descriptions column={2} size="small" bordered>
              <Descriptions.Item label="服务器名称">{wName || '-'}</Descriptions.Item>
              <Descriptions.Item label="数据库类型">{collectMode === 'os' ? '无需数据库' : (wDbType || 'oscar').toUpperCase()}</Descriptions.Item>
              <Descriptions.Item label="SSH 地址">{wSshHost || '本地'}:{wSshPort ?? 22}</Descriptions.Item>
              <Descriptions.Item label="操作系统">{OS_LABELS[wOsType || 'linux'] || wOsType || 'Linux'}</Descriptions.Item>
              <Descriptions.Item label="采集模式">{collectMode === 'os' ? '仅系统' : collectMode === 'db' ? '仅数据库' : '系统 + 数据库'}</Descriptions.Item>
              <Descriptions.Item label="数据库连接">{collectMode === 'os' ? '无需数据库' : `${wDbHost || '-'}:${wDbPort ?? '-'}`}</Descriptions.Item>
              <Descriptions.Item label="数据库类别">{wCategories?.length ?? 0} 项</Descriptions.Item>
              <Descriptions.Item label="系统采集项">{wOsChecks?.length ?? 0} 项</Descriptions.Item>
              <Descriptions.Item label="数据库管控">{wInControl ? '启用' : '停用'}</Descriptions.Item>
              <Descriptions.Item label="应用监控">{apps.length} 个</Descriptions.Item>
              <Descriptions.Item label="日志持久化">{!logEnabled ? '停用（全局未开启）' : (wPersist ? '启用' : '停用')}</Descriptions.Item>
            </Descriptions>
          </div>
        </div>

        <Divider />
        <Space>
          {currentStep > 0 && (
            <Button onClick={() => setCurrentStep(currentStep - 1)}>上一步</Button>
          )}
          {currentStep < 4 ? (
            <Button type="primary" onClick={next}>下一步</Button>
          ) : (
            <Button type="primary" onClick={onSubmit} loading={saving}>
              {editId ? '保存修改' : '添加服务器'}
            </Button>
          )}
          <Button onClick={() => navigate('/servers')}>取消</Button>
        </Space>
      </Form>

      <Modal
        title="连接测试结果"
        open={testOpen}
        onCancel={() => setTestOpen(false)}
        footer={null}
        destroyOnHidden
      >
        {testResult && (
          <Descriptions column={1} size="small" bordered>
            <Descriptions.Item label="SSH 连接">
              <Tag color={testResult.ssh?.ok ? 'green' : 'red'}>{testResult.ssh?.ok ? '成功' : '失败'}</Tag>
              <div style={{ whiteSpace: 'pre-wrap', marginTop: 4 }}>{testResult.ssh?.msg}</div>
            </Descriptions.Item>
            <Descriptions.Item label="数据库连接">
              <Tag color={testResult.db?.ok ? 'green' : 'red'}>{testResult.db?.ok ? '成功' : '失败'}</Tag>
              <div style={{ whiteSpace: 'pre-wrap', marginTop: 4 }}>{testResult.db?.msg}</div>
              {testResult.db?.ok && testResult.db?.version && testResult.db.version.length > 0 && (
                <div style={{ marginTop: 4, color: '#888' }}>版本：{testResult.db.version.join(' / ')}</div>
              )}
            </Descriptions.Item>
          </Descriptions>
        )}
      </Modal>
    </Card>
  )
}
