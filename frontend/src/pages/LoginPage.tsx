// 登录页
import { useState } from 'react'
import { App as AntApp, Button, Form, Input } from 'antd'
import { UserOutlined, LockOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../store/auth'
import { ApiError } from '../api/client'

export default function LoginPage() {
  const { message } = AntApp.useApp()
  const login = useAuth((s) => s.login)
  const navigate = useNavigate()
  const [loading, setLoading] = useState(false)

  const onFinish = async (values: { username: string; password: string }) => {
    setLoading(true)
    try {
      await login(values.username, values.password)
      message.success('登录成功')
      navigate('/')
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : '登录失败'
      message.error(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-bg">
      <div className="login-card">
        <div style={{ textAlign: 'center', marginBottom: 28 }}>
          <div style={{ fontSize: 40 }}>🛰️</div>
          <h1 style={{ margin: '12px 0 4px', fontSize: 22, color: '#1f2937' }}>
            数据库监控管控平台
          </h1>
          <p style={{ color: '#9ca3af', margin: 0, fontSize: 13 }}>
            Oscar / MySQL / PostgreSQL / Oracle
          </p>
        </div>
        <Form onFinish={onFinish} size="large">
          <Form.Item name="username" rules={[{ required: true, message: '请输入用户名' }]}>
            <Input prefix={<UserOutlined />} placeholder="用户名" autoComplete="username" />
          </Form.Item>
          <Form.Item name="password" rules={[{ required: true, message: '请输入密码' }]}>
            <Input.Password prefix={<LockOutlined />} placeholder="密码" autoComplete="current-password" />
          </Form.Item>
          <Button type="primary" htmlType="submit" block loading={loading}>
            登 录
          </Button>
        </Form>
        <div style={{ textAlign: 'center', color: 'rgba(255,255,255,0.45)', fontSize: 12 }}>
          v2.0.0 · FastAPI + React
        </div>
      </div>
    </div>
  )
}
