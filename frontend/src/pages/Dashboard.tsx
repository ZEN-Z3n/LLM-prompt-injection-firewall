import React, { useEffect, useState, useCallback } from 'react';
import { RefreshCw, Shield, ShieldX, ShieldCheck, Activity, AlertTriangle, TrendingUp, Clock } from 'lucide-react';
import { getLogs, getStats } from '../api/client';
import type { LogEntry, StatsResponse } from '../api/client';
import { RiskBadge, ActionBadge, ScoreBar } from '../components/Badges';
import { formatDistanceToNow } from '../utils/time';

export default function Dashboard() {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [autoRefresh, setAutoRefresh] = useState(true);

  const fetchData = useCallback(async () => {
    try {
      const [logsData, statsData] = await Promise.all([
        getLogs(1, 25),
        getStats(7),
      ]);
      setLogs(logsData.items);
      setStats(statsData);
    } catch (err) {
      console.error('Failed to fetch data:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  useEffect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, [autoRefresh, fetchData]);

  const statCards = stats ? [
    {
      label: 'Total Scans',
      value: stats.total_scans.toLocaleString(),
      icon: Activity,
      color: 'text-black',
      bg: 'bg-black/10',
    },
    {
      label: 'Blocked',
      value: stats.blocked_count.toLocaleString(),
      sub: `${stats.blocked_pct}%`,
      icon: ShieldX,
      color: 'text-black',
      bg: 'bg-black/10',
    },
    {
      label: 'Sanitized',
      value: stats.sanitized_count.toLocaleString(),
      icon: AlertTriangle,
      color: 'text-black',
      bg: 'bg-black/10',
    },
    {
      label: 'False Positive Rate',
      value: `${stats.false_positive_rate}%`,
      icon: TrendingUp,
      color: 'text-black',
      bg: 'bg-black/10',
    },
  ] : [];

  return (
    <div className="p-8 space-y-8 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Security Dashboard</h1>
          <p className="text-gray-400 text-sm mt-1">Real-time prompt injection monitoring</p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setAutoRefresh(a => !a)}
            className={`btn-secondary text-xs ${autoRefresh ? 'text-success-400 border-success-500/20' : ''}`}
          >
            <div className={`w-2 h-2 rounded-full ${autoRefresh ? 'bg-success-400 animate-pulse' : 'bg-gray-500'}`} />
            {autoRefresh ? 'Live' : 'Paused'}
          </button>
          <button onClick={fetchData} className="btn-secondary">
            <RefreshCw className="w-4 h-4" />
            Refresh
          </button>
        </div>
      </div>

      {/* Stats row */}
      {loading ? (
        <div className="grid grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="rounded-xl animate-pulse h-24 bg-surface-700" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-4 gap-4">
          {statCards.map(({ label, value, sub, icon: Icon, color, bg }) => (
            <div key={label} className="rounded-xl p-5 bg-brand-200 shadow-sm shadow-brand-400/20 transition-transform hover:scale-[1.02]">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-xs text-surface-800 font-semibold uppercase tracking-wider">{label}</p>
                  <p className="text-3xl font-bold text-black mt-2">{value}</p>
                  {sub && <span className="inline-block mt-2 px-2 py-0.5 bg-black rounded-full text-[10px] text-brand-400 font-bold">{sub}</span>}
                </div>
                <div className={`w-10 h-10 rounded-xl ${bg} flex items-center justify-center`}>
                  <Icon className={`w-5 h-5 ${color}`} />
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Live feed */}
      <div className="card">
        <div className="flex items-center justify-between mb-5">
          <div className="flex items-center gap-2">
            <Shield className="w-5 h-5 text-white" />
            <h2 className="font-semibold text-white">Live Scan Feed</h2>
            {autoRefresh && (
              <span className="text-xs text-gray-500 flex items-center gap-1">
                <div className="w-1.5 h-1.5 rounded-full bg-brand-400 animate-pulse" />
                Live
              </span>
            )}
          </div>
          <span className="text-xs text-gray-500">{logs.length} entries</span>
        </div>

        {loading ? (
          <div className="space-y-2">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="h-14 rounded-xl bg-white/3 animate-pulse" />
            ))}
          </div>
        ) : logs.length === 0 ? (
          <div className="text-center py-16 text-gray-500">
            <ShieldCheck className="w-12 h-12 mx-auto mb-3 text-gray-600" />
            <p className="text-sm">No scans yet. Use the Test Console to run a scan.</p>
          </div>
        ) : (
          <div className="space-y-2">
            {logs.map(log => (
              <ScanRow key={log.id} log={log} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function ScanRow({ log }: { log: LogEntry }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      className={`scan-row flex-col items-start gap-2 ${
        log.risk_level === 'HIGH' ? 'border-danger-500/20' :
        log.risk_level === 'MEDIUM' ? 'border-warning-500/10' : ''
      }`}
      onClick={() => setExpanded(e => !e)}
    >
      <div className="flex items-center gap-4 w-full">
        {/* Risk indicator */}
        <div className={`w-1.5 h-8 rounded-full flex-shrink-0 ${
          log.risk_level === 'HIGH' ? 'bg-danger-500 glow-red' :
          log.risk_level === 'MEDIUM' ? 'bg-warning-500' : 'bg-success-500'
        }`} />

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <RiskBadge level={log.risk_level} />
            <ActionBadge action={log.action_taken} />
            <span className="text-xs text-gray-500 font-mono">{log.source_name}</span>
          </div>
          <p className="text-xs text-gray-500 truncate">{log.raw_snippet}</p>
        </div>

        <div className="flex items-center gap-4 flex-shrink-0">
          <div className="w-24">
            <ScoreBar score={log.risk_score} />
          </div>
          <div className="flex items-center gap-1 text-xs text-gray-500">
            <Clock className="w-3 h-3" />
            {formatDistanceToNow(log.timestamp)}
          </div>
        </div>
      </div>

      {expanded && (
        <div className="w-full pl-6 animate-slide-up">
          <div className="border-t border-white/5 pt-3 space-y-2">
            <p className="text-xs text-gray-400">
              <span className="text-gray-600">Reason: </span>{log.primary_reason}
            </p>
            {log.matched_patterns.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {log.matched_patterns.slice(0, 6).map(p => (
                  <span key={p} className="layer-badge layer-pattern">{p}</span>
                ))}
                {log.matched_patterns.length > 6 && (
                  <span className="text-xs text-gray-500">+{log.matched_patterns.length - 6} more</span>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
