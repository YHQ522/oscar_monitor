// 与后端 Pydantic 模型对应的 TS 类型

export interface User {
  username: string
  is_admin: boolean
  perms: string[]
  created_at?: string
}

export interface AppConfig {
  name: string
  port: number
  svc_name: string
  svc_mgr: string
  in_control: boolean
  group: string
  start_cmd: string
  stop_cmd: string
  status_cmd: string
}

export interface Server {
  id: string
  name: string
  ssh_host: string
  ssh_port: number
  ssh_user: string
  db_host: string
  db_port: number
  db_user: string
  db_name: string
  db_type: string
  isql_cmd: string
  auto_refresh: number
  os_type: string
  in_control: boolean
  persist_enabled: boolean
  svc_name: string
  svc_mgr: string
  svc_start_cmd: string
  svc_stop_cmd: string
  enabled_categories: string[]
  enabled_os_checks: string[]
  skip_db?: boolean
  apps: AppConfig[]
  has_ssh_pass: boolean
  has_db_pass: boolean
  created_at?: string
}

// 创建/更新服务器时的完整表单（含密码）
export interface QueryResult {
  query: string
  columns: string[]
  rows: string[][]
  raw?: string
  error?: string
}

export interface CollectData {
  server: string
  timestamp: string
  os_info: Record<string, QueryResult & { output?: string; exit_code?: number; load_1m?: string }>
  db_queries: Record<string, Record<string, QueryResult>>
  apps: { name: string; running: boolean; status: string }[]
}

export interface HealthDetail {
  value: string
  score: number
  status?: 'healthy' | 'warning' | 'danger'
}

export interface HealthScore {
  score: number | null
  msg?: string
  details?: Record<string, HealthDetail>
}

export interface TrendPoint {
  ts: string
  cpu_pct?: number
  mem_pct?: number
  sessions?: number
  slow_sql_count?: number
}

export interface LockedIp {
  ip: string
  username: string
  count: number
  since: string
  remaining_min: number
}

export interface LogRecord {
  check_type: string
  error_msg: string
  occur_count: number
  occur_time: string
  exec_user: string
  exec_tool: string
  exec_sql: string
  cost_seconds: number
}

export interface ExportHistoryItem {
  filename: string
  server_count: number
  item_count: number
  time: string
  size: number
  size_str: string
}

export interface LogDbConfig {
  db_type?: string
  host?: string
  port?: number
  user?: string
  pass?: string | boolean
  dbname?: string
  isql?: string
  ssh_host?: string
  ssh_port?: number
  ssh_user?: string
  ssh_pass?: string | boolean
}

export interface NotifyConfig {
  enabled?: boolean
  webhook_url?: string
  email_to?: string
  email_from?: string
  email_smtp_host?: string
  email_smtp_port?: number
  email_smtp_user?: string
  email_smtp_pass?: string | boolean
  min_interval?: number
  on_health_below?: number
}

export interface SysConfig {
  log_db?: LogDbConfig
  log_enabled?: boolean
  server_db_enabled?: boolean
  log_retention_days?: number
  collect_workers?: number
  port?: number
  export_schedule?: Record<string, unknown>
  storage_backend?: string
  trend_retention_days?: number
  ssh_connect_timeout?: number
  ssh_exec_timeout?: number
  notify?: NotifyConfig
}

export interface CategoryMeta {
  id: string
  label: string
  icon: string
}

export interface QuerySetMeta {
  label: string
  queries: Record<string, string>
}
