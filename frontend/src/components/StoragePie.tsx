// 存储空间分布饼图：解析 schema_space 类查询结果为饼图
import { useMemo } from 'react'
import { Empty, Typography } from 'antd'
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip, Legend } from 'recharts'
import type { QueryResult } from '../api/types'

const COLORS = ['#4f46e5', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4', '#ec4899', '#84cc16']

function parseNum(v: string): number {
  const m = String(v).match(/([\d.]+)/)
  return m ? Number(m[1]) : 0
}

export default function StoragePie({ result }: { result?: QueryResult }) {
  const data = useMemo(() => {
    if (!result?.rows?.length) return []
    const items = result.rows
      .map((row) => ({ name: String(row[0] || '未知'), value: parseNum(row[1] || '0') }))
      .filter((x) => x.value > 0)
      .sort((a, b) => b.value - a.value)
      .slice(0, 8)
    return items
  }, [result])

  if (!data.length) {
    return <Empty description="暂无存储分布数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
  }

  return (
    <div>
      <ResponsiveContainer width="100%" height={240}>
        <PieChart>
          <Pie data={data} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={90} label={(e: { name: string; percent: number }) => `${e.name} ${Math.round(e.percent * 100)}%`}>
            {data.map((_, i) => (
              <Cell key={i} fill={COLORS[i % COLORS.length]} />
            ))}
          </Pie>
          <Tooltip formatter={(v: number) => [`${v}`, '占用']} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
        </PieChart>
      </ResponsiveContainer>
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        注：数值单位以各数据库输出为准（MB/GB 等），此处仅取数值大小作占比。
      </Typography.Text>
    </div>
  )
}
