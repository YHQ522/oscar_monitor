// Web SQL 终端：只读查询（语法高亮按需引入）
import { useEffect, useState } from 'react'
import { Card, Select, Input, Button, Space, Tag, Typography } from 'antd'
import { App as AntApp } from 'antd'
import { PlayCircleOutlined } from '@ant-design/icons'
// 按需引入：仅注册 SQL 语言 + 一个主题，避免引入全部语言
// 注意：必须用 PrismLight（refractor 格式），Light 是 lowlight 格式不兼容
import { PrismLight as SyntaxHighlighter } from 'react-syntax-highlighter'
import sqlLang from 'react-syntax-highlighter/dist/esm/languages/prism/sql'
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { api } from '../api/client'
import QueryTable from '../components/QueryTable'
import type { Server, QueryResult } from '../api/types'

SyntaxHighlighter.registerLanguage('sql', sqlLang)

const SAFE_PREFIX = '-- 仅支持 SELECT / WITH / EXPLAIN / SHOW / DESC\n\n'
const HISTORY_KEY = 'oscar_sql_history'

function loadHistory(): string[] {
  try {
    return JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]')
  } catch {
    return []
  }
}

function saveHistory(sqls: string[]) {
  try {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(sqls.slice(0, 20)))
  } catch {
    /* ignore */
  }
}

export default function SqlTerminalPage() {
  const { message } = AntApp.useApp()
  const [servers, setServers] = useState<Server[]>([])
  const [serverId, setServerId] = useState<string>('')
  const [sql, setSql] = useState(SAFE_PREFIX + 'SELECT 1;')
  const [history, setHistory] = useState<string[]>(loadHistory)
  const [result, setResult] = useState<QueryResult | null>(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.get<Server[]>('/api/servers').then(setServers).catch((e) => message.error(e.message))
  }, [])

  const run = async () => {
    if (!serverId) {
      message.warning('请选择服务器')
      return
    }
    const statement = sql.replace(SAFE_PREFIX, '').trim()
    if (!statement) {
      message.warning('请输入 SQL')
      return
    }
    setRunning(true)
    setError(null)
    try {
      const data = await api.post<QueryResult>(`/api/servers/${serverId}/sql-query`, { sql: statement })
      setResult(data)
      // 记录历史（去重、最多 20 条）
      setHistory((prev) => {
        const next = [statement, ...prev.filter((h) => h !== statement)].slice(0, 20)
        saveHistory(next)
        return next
      })
    } catch (e) {
      setError((e as Error).message)
      setResult(null)
    } finally {
      setRunning(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault()
      run()
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <h2 style={{ margin: 0 }}>SQL 终端（只读）</h2>
      <Tag color="warning">仅允许只读查询，所有写入/DDL 语句会被拒绝</Tag>

      <Card size="small">
        <Space style={{ marginBottom: 12 }} wrap>
          <Select
            style={{ width: 260 }}
            placeholder="选择服务器"
            value={serverId || undefined}
            onChange={setServerId}
            options={servers.map((s) => ({ value: s.id, label: `${s.name} (${s.db_type})` }))}
          />
          <Button type="primary" icon={<PlayCircleOutlined />} onClick={run} loading={running}>
            执行 (Ctrl+Enter)
          </Button>
        </Space>
        {history.length > 0 && (
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 12, color: '#8a94a6', marginBottom: 4 }}>最近执行：</div>
            <Space size={4} wrap>
              {history.slice(0, 8).map((h) => (
                <Tag
                  key={h}
                  style={{ cursor: 'pointer', maxWidth: 240, overflow: 'hidden', textOverflow: 'ellipsis' }}
                  onClick={() => setSql(SAFE_PREFIX + h)}
                  title={h}
                >
                  {h.length > 28 ? h.slice(0, 28) + '…' : h}
                </Tag>
              ))}
            </Space>
          </div>
        )}
        <Input.TextArea
          value={sql}
          onChange={(e) => setSql(e.target.value)}
          onKeyDown={handleKeyDown}
          rows={8}
          style={{ fontFamily: 'Consolas, monospace', fontSize: 13 }}
        />
        <div style={{ marginTop: 10 }}>
          <div style={{ fontSize: 12, color: '#8a94a6', marginBottom: 4 }}>语法高亮预览</div>
          <SyntaxHighlighter
            language="sql"
            style={oneDark}
            customStyle={{ margin: 0, borderRadius: 6, fontSize: 13, maxHeight: 240, overflow: 'auto' }}
          >
            {sql.replace(SAFE_PREFIX, '').trim() || 'SELECT 1;'}
          </SyntaxHighlighter>
        </div>
      </Card>

      {error && (
        <Card size="small">
          <Typography.Text type="danger">{error}</Typography.Text>
        </Card>
      )}
      {result && (
        <Card size="small" title="查询结果">
          <QueryTable result={result} />
        </Card>
      )}
    </div>
  )
}
