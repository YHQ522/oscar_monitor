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
import { api, ApiError } from '../api/client'
import QueryTable from '../components/QueryTable'
import type { Server, QueryResult } from '../api/types'

SyntaxHighlighter.registerLanguage('sql', sqlLang)

const SAFE_PREFIX = '-- 仅支持 SELECT / WITH / EXPLAIN / SHOW / DESC\n\n'
const HISTORY_KEY = 'oscar_sql_history'

// 常用只读语句模板，按数据库类型推荐（点击填入执行窗口）
const SQL_SNIPPETS: Record<string, { label: string; sql: string }[]> = {
  oscar: [
    { label: '版本信息', sql: 'SELECT VERSION();' },
    { label: '当前连接数', sql: 'SELECT COUNT(*) AS CONNECTION_COUNT FROM V_SYS_SESSIONS;' },
    { label: '连接来源分布', sql: 'SELECT COUNT(*), USER_IP FROM V_SYS_SESSIONS GROUP BY USER_IP ORDER BY COUNT(*) DESC;' },
    { label: '活跃 SQL', sql: 'SELECT "SESSION ID", "CURRENT SQL", USER_IP, "CURRENT USER" FROM V_SYS_SESSIONS WHERE "CURRENT SQL" IS NOT NULL;' },
    { label: '慢 SQL Top20', sql: 'SELECT "TIME(s)", SQL FROM V_SYS_TOP_COST_SQLS WHERE "TIME(s)" > 0.5 ORDER BY "TIME(s)" DESC LIMIT 20;' },
    { label: '阻塞会话', sql: 'SELECT * FROM V$LOCK WHERE BLOCK=1;' },
    { label: '等待链', sql: 'SELECT * FROM V$WAIT_CHAINS;' },
    { label: '未提交事务', sql: 'SELECT COUNT(*) AS NON_AUTO_COMMIT_COUNT FROM V$TRANSACTION WHERE EXPLICIT_TRANS=\'t\';' },
    { label: '实例内存', sql: 'SELECT * FROM V$GLOBAL_MEMORY;' },
    { label: '表空间占用', sql: 'SELECT TRUNC(SUM(B.SIZE)/1024/1024,2)||\' MB\' TABLE_SPACE FROM SYS_CLASS A, V_SEGMENT_INFO B WHERE RELSID = SEGID AND RELNAMESPACE != 11 AND RELKIND = \'r\';' },
    { label: '表数量统计', sql: 'SELECT COUNT(*) TOTAL_TABLE_NUM FROM SYS_CLASS WHERE RELNAMESPACE != 11 AND RELKIND = \'r\';' },
  ],
  mysql: [
    { label: '版本信息', sql: 'SELECT VERSION();' },
    { label: '当前连接数', sql: "SHOW STATUS LIKE 'Threads_connected';" },
    { label: '进程列表', sql: 'SHOW FULL PROCESSLIST;' },
    { label: '慢查询开关', sql: "SHOW VARIABLES LIKE 'slow_query_log%';" },
    { label: '慢查询阈值', sql: "SHOW VARIABLES LIKE 'long_query_time';" },
    { label: 'InnoDB 状态', sql: 'SHOW ENGINE INNODB STATUS;' },
    { label: '数据库列表', sql: 'SHOW DATABASES;' },
    { label: '当前会话信息', sql: 'SELECT * FROM information_schema.PROCESSLIST;' },
    { label: 'InnoDB 事务', sql: 'SELECT * FROM information_schema.INNODB_TRX;' },
    { label: '表数据量 Top20', sql: 'SELECT TABLE_SCHEMA, TABLE_NAME, TABLE_ROWS FROM information_schema.TABLES ORDER BY TABLE_ROWS DESC LIMIT 20;' },
  ],
  postgresql: [
    { label: '版本信息', sql: 'SELECT version();' },
    { label: '活动会话', sql: 'SELECT pid, usename, state, query_start, query FROM pg_stat_activity WHERE state IS NOT NULL;' },
    { label: '当前连接数', sql: 'SELECT count(*) AS connections FROM pg_stat_activity;' },
    { label: '锁等待', sql: 'SELECT * FROM pg_locks WHERE NOT granted;' },
    { label: '库统计', sql: 'SELECT datname, numbackends, xact_commit, xact_rollback, deadlocks FROM pg_stat_database;' },
    { label: '工作内存参数', sql: 'SHOW work_mem;' },
    { label: '连接上限参数', sql: 'SHOW max_connections;' },
    { label: '表大小 Top20', sql: 'SELECT relname, pg_size_pretty(pg_total_relation_size(relid)) AS total_size FROM pg_catalog.pg_statio_user_tables ORDER BY pg_total_relation_size(relid) DESC LIMIT 20;' },
    { label: '最耗时查询', sql: 'SELECT query, calls, total_exec_time FROM pg_stat_statements ORDER BY total_exec_time DESC LIMIT 20;' },
  ],
  oracle: [
    { label: '版本信息', sql: 'SELECT * FROM V$VERSION;' },
    { label: '会话统计', sql: 'SELECT username, status, COUNT(*) FROM v$session WHERE username IS NOT NULL GROUP BY username, status;' },
    { label: '活动会话', sql: 'SELECT sid, serial#, status, username, program FROM v$session WHERE status = \'ACTIVE\';' },
    { label: '阻塞会话', sql: 'SELECT * FROM v$lock WHERE block = 1;' },
    { label: '锁等待', sql: 'SELECT * FROM dba_blockers;' },
    { label: '表空间用量', sql: 'SELECT tablespace_name, ROUND(SUM(bytes)/1024/1024, 2) AS mb FROM dba_data_files GROUP BY tablespace_name;' },
    { label: '最耗时 SQL', sql: 'SELECT sql_id, ROUND(elapsed_time/1000000, 2) AS sec, sql_text FROM v$sql ORDER BY elapsed_time DESC FETCH FIRST 20 ROWS ONLY;' },
    { label: 'SGA 内存', sql: 'SELECT * FROM v$sga;' },
    { label: '实例信息', sql: 'SELECT instance_name, status FROM v$instance;' },
  ],
}

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
  const { message, modal } = AntApp.useApp()
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

  const run = async (riskConfirmed = false) => {
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
      const data = await api.post<QueryResult>(`/api/servers/${serverId}/sql-query`, {
        sql: statement,
        risk_confirmed: riskConfirmed,
      })
      setResult(data)
      // 记录历史（去重、最多 20 条）
      setHistory((prev) => {
        const next = [statement, ...prev.filter((h) => h !== statement)].slice(0, 20)
        saveHistory(next)
        return next
      })
    } catch (e) {
      const err = e as ApiError
      const detail = err.message
      // 高危笛卡尔积（无 WHERE 多表）：已被后端直接阻止，弹框说明原因
      if (err.status === 403 && detail.includes('[CARTESIAN_BLOCKED]')) {
        modal.warning({
          title: '⚠ 高危 SQL 已阻止执行',
          content: detail.replace('[CARTESIAN_BLOCKED] ', ''),
          okText: '知道了',
        })
        return
      }
      // 后端静态检测到笛卡尔积风险：弹确认框，用户确认后带标记重发
      if (err.status === 428 && detail.includes('[CARTESIAN_RISK]')) {
        const warning = detail.replace('[CARTESIAN_RISK] ', '')
        modal.confirm({
          title: '⚠ 潜在笛卡尔积风险',
          content: `${warning}。继续执行可能严重消耗数据库资源，确认仍然执行吗？`,
          okText: '仍然执行',
          okButtonProps: { danger: true },
          cancelText: '取消',
          onOk: () => run(true),
        })
        return
      }
      setError(detail)
      setResult(null)
    } finally {
      setRunning(false)
    }
  }

  const removeHistory = (item: string) => {
    setHistory((prev) => {
      const next = prev.filter((h) => h !== item)
      saveHistory(next)
      return next
    })
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault()
      run()
    }
  }

  const currentServer = servers.find((s) => s.id === serverId)
  const snippets = SQL_SNIPPETS[currentServer?.db_type || ''] || []

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
          <Button type="primary" icon={<PlayCircleOutlined />} onClick={() => run()} loading={running}>
            执行 (Ctrl+Enter)
          </Button>
        </Space>
        {snippets.length > 0 && (
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 12, color: '#8a94a6', marginBottom: 4 }}>
              常用语句（{currentServer?.db_type?.toUpperCase()}，点击填入执行窗口）：
            </div>
            <Space size={4} wrap>
              {snippets.map((s) => (
                <Tag
                  key={s.label}
                  style={{ cursor: 'pointer' }}
                  onClick={() => setSql(SAFE_PREFIX + s.sql)}
                  title={s.sql}
                >
                  {s.label}
                </Tag>
              ))}
            </Space>
          </div>
        )}
        {history.length > 0 && (
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 12, color: '#8a94a6', marginBottom: 4 }}>最近执行：</div>
            <Space size={4} wrap>
              {history.slice(0, 8).map((h) => (
                <Tag
                  key={h}
                  closable
                  style={{ cursor: 'pointer', maxWidth: 280, overflow: 'hidden', textOverflow: 'ellipsis' }}
                  onClick={() => setSql(SAFE_PREFIX + h)}
                  onClose={(e) => {
                    e.preventDefault()
                    removeHistory(h)
                  }}
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
