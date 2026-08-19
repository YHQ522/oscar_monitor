// 数据库内存面板：名称中文化 + 自动单位（KB/MB/GB）+ 占比进度条
import { useMemo } from 'react'
import { Empty } from 'antd'
import QueryTable from './QueryTable'
import type { QueryResult } from '../api/types'

// 神通 V$GLOBAL_MEMORY 名称 → 中文
const NAME_ZH: Record<string, string> = {
  temp_buffer: '临时缓冲区',
  global_chunk: '全局内存块',
  data_buffer: '数据缓冲区',
  log_buffer: '日志缓冲区',
  log_parallel_buffer: '并行日志缓冲区',
  log_header_buffer: '日志头缓冲区',
  bwr_write_buffer: 'BWR 写缓冲区',
  bwr_read_buffer: 'BWR 读缓冲区',
  arch_buffer: '归档缓冲区',
  arch_read_buffer: '归档读缓冲区',
  crf_buffer: 'CRF 缓冲区',
  aio_buffer: 'AIO 缓冲区',
  ha_flush_send_buffer: 'HA 刷新发送缓冲区',
  ha_send_buffer: 'HA 发送缓冲区',
  ha_slave_flush_buffer: 'HA 备机刷新缓冲区',
  dump_pageid_buffer: '页ID转储缓冲区',
  bct_flushed_buffer: 'BCT 已刷新缓冲区',
  bct_write_buffer: 'BCT 写缓冲区',
  bct_flush_temp_buffer: 'BCT 临时刷新缓冲区',
  chunk_holder: '内存块持有者',
  thread_info: '线程信息',
  rdstat: '重做统计',
  env: '环境变量',
  encoding: '字符编码',
  lib_xml: 'XML 库',
  lib_ssl: 'SSL 库',
  brcmd: 'BR 命令',
  asm: 'ASM',
  unclassified: '未分类',
  init: '初始化',
  other: '其他',
  shared_buffers: '共享缓冲区',
  effective_cache_size: '有效缓存大小',
  work_mem: '工作内存',
  maintenance_work_mem: '维护工作内存',
  wal_buffers: 'WAL 缓冲区',
  autovacuum_work_mem: '自动清理工作内存',
  max_connections: '最大连接数',
}

// 解析带单位的数值字符串 → 字节数；解析失败返回 null
function parseBytes(v: unknown): number | null {
  if (v == null || v === '') return null
  const s = String(v).trim().replace(',', '')
  const m = s.match(/^([\d.]+)\s*([GMKTB]?)i?B?$/i)
  if (!m) return null
  const n = parseFloat(m[1])
  if (isNaN(n)) return null
  const u = (m[2] || '').toUpperCase()
  const mult: Record<string, number> = { T: 1099511627776, G: 1073741824, M: 1048576, K: 1024, B: 1, '': 1 }
  return n * (mult[u] ?? 1)
}

function fmtBytes(b: number): string {
  if (b >= 1073741824) return (b / 1073741824).toFixed(2) + ' GB'
  if (b >= 1048576) return (b / 1048576).toFixed(2) + ' MB'
  if (b >= 1024) return (b / 1024).toFixed(1) + ' KB'
  return b + ' B'
}

interface Props {
  result?: QueryResult
  title?: string
}

export default function DbMemoryPanel({ result, title }: Props) {
  const items = useMemo(() => {
    if (!result?.rows?.length || !result.columns?.length) return null
    // 找出名称列与数值列（约定：名称为第一列，数值为最后一列；列名含 SIZE/设置值/VALUE）
    const cols = result.columns.map((c) => String(c).toUpperCase())
    let nameIdx = -1
    let sizeIdx = -1
    for (let i = 0; i < cols.length; i++) {
      const c = cols[i]
      if (nameIdx < 0 && (c.includes('NAME') || c === 'COMPONENT')) nameIdx = i
      if (sizeIdx < 0 && i > 0 && (c.includes('SIZE') || c.includes('VALUE') || c === 'SETTING')) sizeIdx = i
    }
    if (nameIdx < 0) nameIdx = 0
    if (sizeIdx < 0) sizeIdx = result.columns.length - 1
    if (nameIdx === sizeIdx && result.columns.length > 1) sizeIdx = result.columns.length - 1

    const parsed = result.rows.map((row, ri) => {
      const raw = row[sizeIdx]
      let bytes = parseBytes(raw)
      // 第三列为单位列（如 pg_settings.unit='8kB'）时换算
      if (bytes === null && result.columns.length > 2 && row.length > 2) {
        const unit = String(row[2] ?? '').trim()
        const um = unit.match(/^(\d+)?\s*(kB|MB|GB|KB|B)/i)
        const num = parseFloat(String(raw))
        if (um && !isNaN(num)) {
          const mult = parseInt(um[1] || '1', 10)
          const u = um[2].toUpperCase()
          const base: Record<string, number> = { B: 1, KB: 1024, MB: 1048576, GB: 1073741824 }
          bytes = num * mult * (base[u] ?? 1)
        }
      }
      return {
        key: ri,
        name: NAME_ZH[String(row[nameIdx] ?? '').trim().toLowerCase()] || String(row[nameIdx] ?? ''),
        bytes,
        raw: String(raw ?? ''),
      }
    })

    // 全部解析成功才启用面板；否则降级为通用表格
    if (parsed.some((p) => p.bytes === null)) return null
    return parsed
  }, [result])

  if (!items) {
    // 无法解析（如 MySQL 混合状态变量）→ 退回通用表格
    if (result && result.rows?.length) return <QueryTable result={result} title={title} />
    return <Empty description="暂无数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
  }

  const total = items.reduce((a, i) => a + (i.bytes ?? 0), 0)
  const max = Math.max(...items.map((i) => i.bytes ?? 0), 1)

  return (
    <div>
      {title && (
        <div style={{ fontWeight: 600, marginBottom: 8 }}>{title}</div>
      )}
      <div style={{ marginBottom: 12 }}>
        <span style={{ fontSize: 28, fontWeight: 800, fontFamily: 'Consolas,monospace', color: '#4f46e5' }}>
          {fmtBytes(total)}
        </span>
        <span style={{ marginLeft: 8, color: '#64748b', fontSize: 12 }}>内存总量合计</span>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {items.map((it) => {
          const pct = it.bytes === 0 ? 0 : Math.max(2, Math.round(((it.bytes ?? 0) / max) * 100))
          return (
            <div key={it.key}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
                <span style={{ fontSize: 13 }}>{it.name}</span>
                <span style={{ fontFamily: 'Consolas,monospace', fontSize: 12, color: it.bytes ? '#1e293b' : '#94a3b8', fontWeight: 600 }}>
                  {it.bytes ? fmtBytes(it.bytes) : '未使用'}
                </span>
              </div>
              <div style={{ height: 8, background: '#eef2f7', borderRadius: 4, overflow: 'hidden' }}>
                <div
                  style={{
                    height: '100%',
                    width: `${pct}%`,
                    background: it.bytes === 0 ? 'transparent' : 'linear-gradient(90deg,#6366f1,#8b5cf6)',
                    borderRadius: 4,
                    transition: 'width 0.4s ease',
                  }}
                />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
