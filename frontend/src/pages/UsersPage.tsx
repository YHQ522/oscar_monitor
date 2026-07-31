// 用户管理 + IP 封禁管理
import { useEffect, useState } from 'react'
import { Table, Button, Space, Tag, Popconfirm, Modal, Form, Input, Switch, Select, Tabs, Badge } from 'antd'
import { App as AntApp } from 'antd'
import { PlusOutlined, EditOutlined, DeleteOutlined, UnlockOutlined } from '@ant-design/icons'
import { api } from '../api/client'
import type { User, LockedIp } from '../api/types'

const PERMISSION_LABELS: Record<string, string> = {
  dashboard: '全局监控',
  servers_view: '服务管理(查看)',
  servers_edit: '服务管理(编辑)',
  control_view: '启停管控(查看)',
  control_exec: '启停管控(执行)',
  admin: '系统管理',
}

export default function UsersPage() {
  const { message } = AntApp.useApp()
  const [users, setUsers] = useState<User[]>([])
  const [locked, setLocked] = useState<LockedIp[]>([])
  const [loading, setLoading] = useState(true)
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<User | null>(null)
  const [form] = Form.useForm()

  const load = async () => {
    setLoading(true)
    try {
      const [u, l] = await Promise.all([
        api.get<User[]>('/api/users'),
        api.get<{ locked: LockedIp[] }>('/api/admin/locked-ips'),
      ])
      setUsers(u)
      setLocked(l.locked)
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const openAdd = () => {
    setEditing(null)
    setModalOpen(true)
  }

  const openEdit = (user: User) => {
    setEditing(user)
    setModalOpen(true)
  }

  // Modal 打开（Form 挂载）后再填充表单，避免 useForm 未连接警告
  useEffect(() => {
    if (!modalOpen) return
    if (editing) {
      form.setFieldsValue({ username: editing.username, is_admin: editing.is_admin, perms: editing.perms })
    } else {
      form.resetFields()
      form.setFieldsValue({ is_admin: false, perms: ['dashboard'] })
    }
  }, [modalOpen, editing, form])

  const save = async () => {
    const values = await form.validateFields()
    try {
      if (editing) {
        await api.put(`/api/users/${editing.username}`, { is_admin: values.is_admin, perms: values.perms, password: values.password || undefined })
        message.success('已更新')
      } else {
        await api.post('/api/users', values)
        message.success('已创建')
      }
      setModalOpen(false)
      load()
    } catch (e) {
      message.error((e as Error).message)
    }
  }

  const remove = async (user: User) => {
    try {
      await api.delete(`/api/users/${user.username}`)
      message.success('已删除')
      load()
    } catch (e) {
      message.error((e as Error).message)
    }
  }

  const unlock = async (ip: string) => {
    try {
      await api.post('/api/admin/unlock-ip', { ip })
      message.success('已解锁')
      load()
    } catch (e) {
      message.error((e as Error).message)
    }
  }

  const userColumns = [
    { title: '用户名', dataIndex: 'username' },
    {
      title: '角色',
      dataIndex: 'is_admin',
      render: (v: boolean) => (v ? <Tag color="gold">管理员</Tag> : <Tag>普通用户</Tag>),
    },
    {
      title: '权限',
      dataIndex: 'perms',
      render: (perms: string[]) => (
        <Space size={4} wrap>
          {(perms || []).map((p) => (
            <Tag key={p} color="blue">{PERMISSION_LABELS[p] || p}</Tag>
          ))}
        </Space>
      ),
    },
    { title: '创建时间', dataIndex: 'created_at' },
    {
      title: '操作',
      fixed: 'right' as const,
      width: 150,
      render: (_: unknown, r: User) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(r)}>编辑</Button>
          <Popconfirm title={`确认删除 ${r.username}？`} onConfirm={() => remove(r)}>
            <Button size="small" danger icon={<DeleteOutlined />} disabled={r.username === 'admin'}>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  const lockedColumns = [
    { title: 'IP 地址', dataIndex: 'ip' },
    { title: '尝试用户', dataIndex: 'username' },
    { title: '失败次数', dataIndex: 'count' },
    { title: '封禁时间', dataIndex: 'since' },
    { title: '剩余(分钟)', dataIndex: 'remaining_min' },
    {
      title: '操作',
      fixed: 'right' as const,
      width: 100,
      render: (_: unknown, r: LockedIp) => (
        <Button size="small" icon={<UnlockOutlined />} onClick={() => unlock(r.ip)}>解锁</Button>
      ),
    },
  ]

  return (
    <div>
      <Tabs
        items={[
          {
            key: 'users',
            label: '用户管理',
            children: (
              <div>
                <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
                  <Button type="primary" icon={<PlusOutlined />} onClick={openAdd}>添加用户</Button>
                </div>
                <Table rowKey="username" loading={loading} dataSource={users} columns={userColumns} pagination={false} scroll={{ x: 'max-content' }} />
              </div>
            ),
          },
          {
            key: 'locked',
            label: (
              <span>
                IP 封禁 <Badge count={locked.length} size="small" style={{ backgroundColor: '#f5222d' }} />
              </span>
            ),
            children: <Table rowKey="ip" dataSource={locked} columns={lockedColumns} pagination={false} scroll={{ x: 'max-content' }} />,
          },
        ]}
      />

      <Modal title={editing ? `编辑用户 ${editing.username}` : '添加用户'} open={modalOpen} onOk={save} onCancel={() => setModalOpen(false)} destroyOnHidden>
        <Form form={form} layout="vertical">
          {!editing && (
            <Form.Item name="username" label="用户名" rules={[{ required: true, message: '必填' }]}>
              <Input />
            </Form.Item>
          )}
          <Form.Item
            name="password"
            label={editing ? '新密码（留空不修改）' : '密码'}
            rules={editing ? [] : [{ required: true, message: '必填' }, { min: 6, message: '至少 6 位' }]}
          >
            <Input.Password />
          </Form.Item>
          <Form.Item name="is_admin" label="管理员" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="perms" label="权限">
            <Select
              mode="multiple"
              options={Object.entries(PERMISSION_LABELS).map(([v, l]) => ({ value: v, label: l }))}
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
