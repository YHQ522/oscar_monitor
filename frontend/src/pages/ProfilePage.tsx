// 个人中心：修改密码
import { Card, Form, Input, Button, Descriptions, Tag } from 'antd'
import { App as AntApp } from 'antd'
import { LockOutlined } from '@ant-design/icons'
import { api } from '../api/client'
import { useAuth } from '../store/auth'

const PERMISSION_LABELS: Record<string, string> = {
  dashboard: '全局监控',
  servers_view: '服务管理(查看)',
  servers_edit: '服务管理(编辑)',
  control_view: '启停管控(查看)',
  control_exec: '启停管控(执行)',
  admin: '系统管理',
}

export default function ProfilePage() {
  const { message } = AntApp.useApp()
  const user = useAuth((s) => s.user)
  const [form] = Form.useForm()

  const submit = async () => {
    try {
      const values = await form.validateFields()
      await api.put('/api/auth/password', values)
      message.success('密码修改成功，请重新登录')
      form.resetFields()
      useAuth.getState().logout()
      window.location.href = '/login'
    } catch (e) {
      message.error((e as Error).message)
    }
  }

  return (
    <div style={{ maxWidth: 640, width: '100%' }}>
      <h2>个人中心</h2>
      <Card size="small" style={{ marginBottom: 16 }}>
        <Descriptions column={1} size="small">
          <Descriptions.Item label="用户名">{user?.username}</Descriptions.Item>
          <Descriptions.Item label="角色">
            {user?.is_admin ? <Tag color="gold">管理员</Tag> : <Tag>普通用户</Tag>}
          </Descriptions.Item>
          <Descriptions.Item label="权限">
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
              {(user?.perms || []).map((p) => (
                <Tag key={p} color="blue">{PERMISSION_LABELS[p] || p}</Tag>
              ))}
            </div>
          </Descriptions.Item>
        </Descriptions>
      </Card>
      <Card title="修改密码" size="small">
        <Form form={form} layout="vertical">
          <Form.Item name="old_password" label="原密码" rules={[{ required: true, message: '必填' }]}>
            <Input.Password prefix={<LockOutlined />} />
          </Form.Item>
          <Form.Item name="new_password" label="新密码" rules={[{ required: true, message: '必填' }, { min: 6, message: '至少 6 位' }]}>
            <Input.Password />
          </Form.Item>
          <Button type="primary" onClick={submit}>确认修改</Button>
        </Form>
      </Card>
    </div>
  )
}
