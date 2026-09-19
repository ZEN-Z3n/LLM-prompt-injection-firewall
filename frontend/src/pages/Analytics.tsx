import React, { useEffect, useState } from 'react';
import {
  BarChart, Bar, PieChart, Pie, Cell, LineChart, Line,
  XAxis, YAxis, Tooltip, ResponsiveContainer,
} from 'recharts';
import { BarChart3, TrendingUp, PieChart as PieIcon } from 'lucide-react';
import { getStats } from '../api/client';
import type { StatsResponse } from '../api/client';

const RISK_COLORS: Record<string, string> = {
  HIGH: '#ef4444',
  MEDIUM: '#f59e0b',
  LOW: '#22c55e',
};

const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="card p-3 text-xs">
      <p className="text-gray-400 mb-1">{label}</p>
      {payload.map((p: any) => (
        <p key={p.name} style={{ color: p.color }}>{p.name}: {p.value}</p>
      ))}
    </div>
  );
};

export default function Analytics() {
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [days, setDays] = useState(30);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    getStats(days)
      .then(setStats)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [days]);

  const pieData = stats
    ? Object.entries(stats.risk_distribution).map(([name, value]) => ({ name, value }))
    : [];

  const topPatterns = stats?.top_patterns.slice(0, 8) ?? [];

  return (
    <div className="p-8 space-y-8 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Analytics</h1>
          <p className="text-gray-400 text-sm mt-1">Attack patterns and risk trends</p>
        </div>
        <div className="flex items-center gap-2">
          {[7, 14, 30, 90].map(d => (
            <button
              key={d}
              onClick={() => setDays(d)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                days === d
                  ? 'bg-brand-600/30 text-brand-300 border border-brand-500/30'
                  : 'text-gray-400 hover:text-gray-200 hover:bg-white/5'
              }`}
            >
              {d}d
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="grid grid-cols-2 gap-6">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="card h-72 animate-pulse bg-surface-700" />
          ))}
        </div>
      ) : (
        <>
          {/* Top row */}
          <div className="grid grid-cols-3 gap-6">
            {/* Scans over time */}
            <div className="card col-span-2">
              <div className="flex items-center gap-2 mb-6">
                <TrendingUp className="w-4 h-4 text-brand-400" />
                <h2 className="font-semibold text-white text-sm">Scans Over Time</h2>
              </div>
              <ResponsiveContainer width="100%" height={200}>
                <LineChart data={stats?.scans_over_time ?? []}>
                  <XAxis
                    dataKey="date"
                    tick={{ fill: '#6b7280', fontSize: 10 }}
                    tickLine={false}
                    axisLine={false}
                    interval="preserveStartEnd"
                    tickFormatter={d => d.slice(5)}
                  />
                  <YAxis tick={{ fill: '#6b7280', fontSize: 10 }} tickLine={false} axisLine={false} />
                  <Tooltip content={<CustomTooltip />} />
                  <Line
                    type="monotone"
                    dataKey="count"
                    name="Scans"
                    stroke="#3d5ff5"
                    strokeWidth={2}
                    dot={false}
                    activeDot={{ r: 4, fill: '#628af9' }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>

            {/* Risk distribution pie */}
            <div className="card">
              <div className="flex items-center gap-2 mb-4">
                <PieIcon className="w-4 h-4 text-brand-400" />
                <h2 className="font-semibold text-white text-sm">Risk Distribution</h2>
              </div>
              <ResponsiveContainer width="100%" height={150}>
                <PieChart>
                  <Pie
                    data={pieData}
                    cx="50%"
                    cy="50%"
                    innerRadius={45}
                    outerRadius={70}
                    paddingAngle={3}
                    dataKey="value"
                  >
                    {pieData.map((entry, index) => (
                      <Cell
                        key={`cell-${index}`}
                        fill={RISK_COLORS[entry.name] ?? '#6b7280'}
                        opacity={0.85}
                      />
                    ))}
                  </Pie>
                  <Tooltip content={<CustomTooltip />} />
                </PieChart>
              </ResponsiveContainer>
              <div className="space-y-1.5 mt-2">
                {pieData.map(({ name, value }) => (
                  <div key={name} className="flex items-center justify-between text-xs">
                    <div className="flex items-center gap-1.5">
                      <div className="w-2.5 h-2.5 rounded-full" style={{ background: RISK_COLORS[name] }} />
                      <span className="text-gray-400">{name}</span>
                    </div>
                    <span className="text-gray-300 font-medium">{value}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Bottom row */}
          <div className="grid grid-cols-2 gap-6">
            {/* Top attack patterns */}
            <div className="card">
              <div className="flex items-center gap-2 mb-6">
                <BarChart3 className="w-4 h-4 text-brand-400" />
                <h2 className="font-semibold text-white text-sm">Top Attack Patterns</h2>
              </div>
              {topPatterns.length === 0 ? (
                <p className="text-gray-500 text-sm text-center py-8">No patterns detected yet</p>
              ) : (
                <ResponsiveContainer width="100%" height={200}>
                  <BarChart data={topPatterns} layout="vertical" barSize={10}>
                    <XAxis type="number" tick={{ fill: '#6b7280', fontSize: 10 }} tickLine={false} axisLine={false} />
                    <YAxis
                      type="category"
                      dataKey="pattern_id"
                      tick={{ fill: '#9ca3af', fontSize: 10, fontFamily: 'JetBrains Mono' }}
                      tickLine={false}
                      axisLine={false}
                      width={60}
                    />
                    <Tooltip content={<CustomTooltip />} />
                    <Bar dataKey="count" name="Count" fill="#3d5ff5" radius={[0, 4, 4, 0]} opacity={0.8} />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </div>

            {/* Summary stats */}
            <div className="card">
              <h2 className="font-semibold text-white text-sm mb-6">Scan Summary</h2>
              <div className="space-y-4">
                {[
                  { label: 'Total Scans', value: stats?.total_scans ?? 0, color: 'text-brand-400' },
                  { label: 'Blocked', value: stats?.blocked_count ?? 0, color: 'text-danger-400' },
                  { label: 'Sanitized', value: stats?.sanitized_count ?? 0, color: 'text-warning-400' },
                  { label: 'Passed', value: stats?.passed_count ?? 0, color: 'text-success-400' },
                  { label: 'False Positives', value: stats?.false_positive_count ?? 0, color: 'text-gray-400' },
                ].map(({ label, value, color }) => (
                  <div key={label} className="flex items-center justify-between">
                    <span className="text-sm text-gray-400">{label}</span>
                    <span className={`text-sm font-semibold ${color}`}>{value.toLocaleString()}</span>
                  </div>
                ))}
                <div className="divider pt-4">
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-gray-400">Block Rate</span>
                    <span className="text-sm font-semibold text-danger-400">{stats?.blocked_pct ?? 0}%</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
