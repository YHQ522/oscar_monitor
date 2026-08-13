// 系统配置：日志库 + 全局参数 + 告警通知
import { useEffect, useState } from 'react'
import { Card, Form, Input, InputNumber, Select, Switch, Button, Space, Divider, Descriptions, Tag, Alert } from 'antd'
import { App as AntApp } from 'antd'
import { SaveOutlined, ApiOutlined, SendOutlined, BellOutlined } from '@ant-design/icons'
import { api } from '../api/client'
import type { LogDbConfig, NotifyConfig, SysConfig } from '../api/types'

export default function ConfigPage() {
  const { message } = AntApp.useApp()
  // 三个卡片各自独立的表单实例（避免共享一个 useForm 导致字段/校验互相干扰）
  const [formDb] = Form.useForm()
  const [formGlobal] = Form.useForm()
  const [formNotify] = Form.useForm()
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [testingNotify, setTestingNotify] = useState(false)
  const [cfg, setCfg] = useState<SysConfig>({})

  useEffect(() => {
    api.get<SysConfig>('/api/config')
      .then((c) => {
        setCfg(c)
        // 注意：pass / ssh_pass 是后端脱敏后的布尔值，不能回填表单（否则密码框显示 "false"）
        formDb.setFieldsValue({
          db_type: c.log_db?.db_type,
          host: c.log_db?.host,
          port: c.log_db?.port,
          user: c.log_db?.user,
          dbname: c.log_db?.dbname,
          isql: c.log_db?.isql,
          ssh_host: c.log_db?.ssh_host,
          ssh_port: c.log_db?.ssh_port,
          ssh_user: c.log_db?.ssh_user,
        })
        formGlobal.setFieldsValue({
          log_enabled: c.log_enabled,
          log_retention_days: c.log_retention_days,
          collect_workers: c.collect_workers,
          port: c.port,
          trend_retention_days: c.trend_retention_days,
          ssh_connect_timeout: c.ssh_connect_timeout,
          ssh_exec_timeout: c.ssh_exec_timeout,
        })
        formNotify.setFieldsValue({
          notify_enabled: c.notify?.enabled,
          webhook_url: c.notify?.webhook_url,
          email_to: c.notify?.email_to,
          email_from: c.notify?.email_from,
          email_smtp_host: c.notify?.email_smtp_host,
          email_smtp_port: c.notify?.email_smtp_port,
          email_smtp_user: c.notify?.email_smtp_user,
          notify_min_interval: c.notify?.min_interval,
          notify_on_health_below: c.notify?.on_health_below,
        })
      })
      .catch((e) => message.error(e.message))
  }, [formDb, formGlobal, formNotify])

  const save = async () => {
    setSaving(true)
    try {
      const [vDb, vGlobal, vNotify] = await Promise.all([
        formDb.validateFields(),
        formGlobal.validateFields(),
        formNotify.validateFields(),
      ])
      const values = { ...vDb, ...vGlobal, ...vNotify }
      const logDb: LogDbConfig = {
        db_type: values.db_type,
        host: values.host,
        port: values.port,
        user: values.user,
        pass: values.pass,
        dbname: values.dbname,
        isql: values.isql,
        ssh_host: values.ssh_host,
        ssh_port: values.ssh_port,
        ssh_user: values.ssh_user,
        ssh_pass: values.ssh_pass,
      }
      const notify: NotifyConfig = {
        enabled: values.notify_enabled ?? false,
        webhook_url: values.webhook_url,
        email_to: values.email_to,
        email_from: values.email_from,
        email_smtp_host: values.email_smtp_host,
        email_smtp_port: values.email_smtp_port,
        email_smtp_user: values.email_smtp_user,
        email_smtp_pass: values.email_smtp_pass,
        min_interval: values.notify_min_interval,
        on_health_below: values.notify_on_health_below,
      }
      const resp = await api.put<SysConfig>('/api/config', {
        log_db: logDb,
        log_enabled: values.log_enabled,
        log_retention_days: values.log_retention_days,
        collect_workers: values.collect_workers,
        port: values.port,
        trend_retention_days: values.trend_retention_days,
        ssh_connect_timeout: values.ssh_connect_timeout,
        ssh_exec_timeout: values.ssh_exec_timeout,
        notify,
      })
      setCfg(resp)
      message.success('配置已保存')
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  const test = async () => {
    setTesting(true)
    try {
      const values = await formDb.validateFields()
      message.loading('测试中...', 0)
      const result = await api.post<{ ssh: { ok: boolean; msg: string } | null; db: { ok: boolean; msg: string } | null }>(
        '/api/config/test-log-db',
        {
          db_type: values.db_type,
          host: values.host,
          port: values.port,
          user: values.user,
          pass: values.pass,
          dbname: values.dbname,
          isql: values.isql,
          ssh_host: values.ssh_host,
          ssh_port: values.ssh_port,
          ssh_user: values.ssh_user,
          ssh_pass: values.ssh_pass,
        },
      )
      message.destroy()
      if (result.ssh) {
        result.ssh.ok ? message.success(`SSH: ${result.ssh.msg}`) : message.error(`SSH: ${result.ssh.msg}`)
      }
      if (result.db) {
        result.db.ok ? message.success(`数据库: ${result.db.msg}`) : message.error(`数据库: ${result.db.msg}`)
      }
    } catch (e) {
      message.destroy()
      message.error((e as Error).message)
    } finally {
      setTesting(false)
    }
  }

  const onDbTypeChange = (value: string) => {
    // 各类型默认连接参数联动（与"添加服务器"保持一致）
    const defaults: Record<string, { port: number; user: string; db: string; cli: string }> = {
      oscar: { port: 2003, user: 'SYSDBA', db: 'OSRDB', cli: 'isql' },
      mysql: { port: 3306, user: 'root', db: 'mysql', cli: 'mysql' },
      postgresql: { port: 5432, user: 'postgres', db: 'postgres', cli: 'psql' },
      oracle: { port: 1521, user: 'system', db: 'ORCL', cli: 'sqlplus' },
    }
    const d = defaults[value] || defaults.oscar
    formDb.setFieldsValue({ port: d.port, user: d.user, dbname: d.db, isql: d.cli })
  }

  const testNotify = async () => {
    setTestingNotify(true)
    try {
      await save()
      const result = await api.post<{ webhook?: { ok: boolean; msg: string }; email?: { ok: boolean; msg: string }; msg?: string }>(
        '/api/config/test-notify',
        {},
      )
      if (result.msg) {
        message.warning(result.msg)
        return
      }
      if (result.webhook) {
        result.webhook.ok ? message.success(`Webhook: ${result.webhook.msg}`) : message.error(`Webhook: ${result.webhook.msg}`)
      }
      if (result.email) {
        result.email.ok ? message.success(`邮件: ${result.email.msg}`) : message.error(`邮件: ${result.email.msg}`)
      }
      if (!result.webhook && !result.email) {
        message.warning('未配置任何通知渠道')
      }
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setTestingNotify(false)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <h2 style={{ margin: 0 }}>系统配置</h2>

      <Alert
        type="info"
        showIcon
        message={`当前存储后端：${cfg.storage_backend === 'sqlite' ? 'SQLite 数据库' : 'JSON 文件'}`}
        description="存储后端在启动时通过 OSCAR_STORAGE_BACKEND 环境变量决定：json（默认）或 sqlite。"
      />

      <Card title="日志持久化数据库" size="small">
        <Form form={formDb} layout="vertical" initialValues={{ db_type: 'oscar', port: 2003, user: 'SYSDBA', dbname: 'OSRDB', isql: 'isql', ssh_port: 22, ssh_user: 'root' }}>
          <Divider orientation="left">数据库连接</Divider>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 16 }}>
            <Form.Item name="db_type" label="数据库类型">
              <Select
                options={[{ value: 'oscar', label: 'Oscar (神通)' }, { value: 'mysql', label: 'MySQL' }, { value: 'postgresql', label: 'PostgreSQL' }, { value: 'oracle', label: 'Oracle' }]}
                onChange={onDbTypeChange}
              />
            </Form.Item>
            <Form.Item name="host" label="主机">
              <Input placeholder="127.0.0.1" />
            </Form.Item>
            <Form.Item name="port" label="端口">
              <InputNumber min={1} max={65535} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="user" label="用户">
              <Input />
            </Form.Item>
            <Form.Item name="pass" label="密码" extra={cfg.log_db?.pass ? '已保存密码，留空保持' : undefined}>
              <Input.Password placeholder={cfg.log_db?.pass ? '（已保存）' : ''} />
            </Form.Item>
            <Form.Item name="dbname" label="数据库名">
              <Input />
            </Form.Item>
            <Form.Item name="isql" label="CLI 命令">
              <Input placeholder="isql" />
            </Form.Item>
          </div>

          <Divider orientation="left">SSH 隧道（可选）</Divider>
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
            message="什么情况下需要填 SSH？"
            description={
              <>
                当日志库在<strong>远程服务器</strong>、且监控机无法直接连接数据库（本机未安装 CLI 工具或数据库端口不对外开放）时，填写下方 SSH 主机与账号。
                采集端会先 SSH 登录<strong>日志库所在服务器</strong>，再在其本机执行 CLI 读写日志表；留空则在本机直接连接。
                填了 SSH 后，上方「数据库连接」的 host 应填日志库所在服务器的<strong>本地地址</strong>（如 127.0.0.1）。
              </>
            }
          />
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 16 }}>
            <Form.Item name="ssh_host" label="SSH 主机">
              <Input placeholder="留空表示本机直接连接" />
            </Form.Item>
            <Form.Item name="ssh_port" label="SSH 端口">
              <InputNumber min={1} max={65535} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="ssh_user" label="SSH 用户">
              <Input />
            </Form.Item>
            <Form.Item name="ssh_pass" label="SSH 密码" extra={cfg.log_db?.ssh_pass ? '已保存密码' : undefined}>
              <Input.Password placeholder={cfg.log_db?.ssh_pass ? '（已保存）' : ''} />
            </Form.Item>
          </div>

          <Space>
            <Button icon={<ApiOutlined />} onClick={test} loading={testing}>测试连接</Button>
          </Space>
        </Form>
      </Card>

      <Card title="全局参数" size="small">
        <Form form={formGlobal} layout="vertical">
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: 16 }}>
            <Form.Item name="log_enabled" label="启用日志持久化" valuePropName="checked">
              <Switch />
            </Form.Item>
            <Form.Item name="log_retention_days" label="日志保留天数">
              <InputNumber min={1} max={3650} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="collect_workers" label="并发采集线程数">
              <InputNumber min={1} max={32} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="port" label="服务监听端口" extra="重启后生效">
              <InputNumber min={1} max={65535} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="trend_retention_days" label="趋势保留天数">
              <InputNumber min={1} max={365} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="ssh_connect_timeout" label="SSH 连接超时(秒)">
              <InputNumber min={3} max={120} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="ssh_exec_timeout" label="SQL 命令超时(秒)">
              <InputNumber min={10} max={600} style={{ width: '100%' }} />
            </Form.Item>
          </div>
        </Form>
      </Card>

      <Card title={<span><BellOutlined /> 告警通知</span>} size="small">
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message="采集后自动评估：健康分低于阈值或存在采集错误时，通过 Webhook / 邮件推送告警。同一服务器默认 5 分钟内不重复发送（去抖）。"
        />
        <Form form={formNotify} layout="vertical">
          <Divider orientation="left">Webhook</Divider>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 16 }}>
            <Form.Item name="webhook_url" label="Webhook URL">
              <Input placeholder="https://example.com/hook" />
            </Form.Item>
          </div>
          <Divider orientation="left">邮件（SMTP）</Divider>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 16 }}>
            <Form.Item name="email_to" label="收件人（逗号分隔）">
              <Input placeholder="ops@example.com" />
            </Form.Item>
            <Form.Item name="email_from" label="发件人">
              <Input placeholder="oscar-monitor@example.com" />
            </Form.Item>
            <Form.Item name="email_smtp_host" label="SMTP 服务器">
              <Input placeholder="smtp.example.com" />
            </Form.Item>
            <Form.Item name="email_smtp_port" label="SMTP 端口">
              <InputNumber min={1} max={65535} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="email_smtp_user" label="SMTP 用户">
              <Input />
            </Form.Item>
            <Form.Item name="email_smtp_pass" label="SMTP 密码" extra={cfg.notify?.email_smtp_pass ? '已保存密码，留空保持' : undefined}>
              <Input.Password placeholder={cfg.notify?.email_smtp_pass ? '（已保存）' : ''} />
            </Form.Item>
          </div>
          <Divider orientation="left">触发规则</Divider>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 16 }}>
            <Form.Item name="notify_enabled" label="启用告警通知" valuePropName="checked">
              <Switch />
            </Form.Item>
            <Form.Item name="notify_on_health_below" label="健康分阈值(低于触发)">
              <InputNumber min={0} max={100} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="notify_min_interval" label="去抖间隔(秒)">
              <InputNumber min={60} max={86400} style={{ width: '100%' }} />
            </Form.Item>
          </div>
          <Space>
            <Button icon={<SendOutlined />} onClick={testNotify} loading={testingNotify}>保存并发送测试通知</Button>
          </Space>
        </Form>
      </Card>

      <div>
        <Button type="primary" icon={<SaveOutlined />} onClick={save} loading={saving}>
          保存全部配置
        </Button>
      </div>

      <Descriptions title="当前生效配置" column={2} size="small" bordered>
        <Descriptions.Item label="日志持久化">
          <Tag color={cfg.log_enabled ? 'green' : 'default'}>{cfg.log_enabled ? '已启用' : '未启用'}</Tag>
        </Descriptions.Item>
        <Descriptions.Item label="并发采集线程">{cfg.collect_workers ?? '-'}</Descriptions.Item>
        <Descriptions.Item label="服务端口">{cfg.port ?? 5080}</Descriptions.Item>
        <Descriptions.Item label="日志保留天数">{cfg.log_retention_days ?? '-'}</Descriptions.Item>
        <Descriptions.Item label="趋势保留天数">{cfg.trend_retention_days ?? '-'}</Descriptions.Item>
        <Descriptions.Item label="SSH 连接超时">{cfg.ssh_connect_timeout ? `${cfg.ssh_connect_timeout}s` : '-'}</Descriptions.Item>
        <Descriptions.Item label="SQL 命令超时">{cfg.ssh_exec_timeout ? `${cfg.ssh_exec_timeout}s` : '-'}</Descriptions.Item>
        <Descriptions.Item label="告警通知">
          <Tag color={cfg.notify?.enabled ? 'green' : 'default'}>{cfg.notify?.enabled ? '已启用' : '未启用'}</Tag>
        </Descriptions.Item>
        <Descriptions.Item label="存储后端">{cfg.storage_backend ?? 'json'}</Descriptions.Item>
      </Descriptions>
    </div>
  )
}
