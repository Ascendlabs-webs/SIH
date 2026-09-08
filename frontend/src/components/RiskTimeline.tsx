import React from 'react';
import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { AnalysisResult } from '../types';

export function RiskTimeline({ data }: { data: AnalysisResult[] }) {
  const pts = data.map((r, i) => ({
    i: i + 1,
    risk: Number(r.risk_score.toFixed(3)),
    level: r.alert_level,
    t: new Date(r.timestamp).toLocaleTimeString(),
  }));
  return (
    <div className="chart-box">
      {pts.length === 0 ? (
        <div className="empty">No windows yet — start a demo, stream the mic, or upload audio.</div>
      ) : (
        <ResponsiveContainer width="100%" height={220}>
          <AreaChart data={pts} margin={{ top: 8, right: 12, bottom: 0, left: -18 }}>
            <defs>
              <linearGradient id="riskFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#0284c9" stopOpacity={0.35} />
                <stop offset="100%" stopColor="#0284c9" stopOpacity={0.03} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="i" stroke="#64748b" tick={{ fontSize: 11 }} tickLine={false} axisLine={{ stroke: '#e2e8f0' }} label={{ value: 'window', fill: '#64748b', fontSize: 11, position: 'insideBottomRight' }} />
            <YAxis domain={[0, 1]} stroke="#64748b" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} width={34} />
            <Tooltip
              contentStyle={{ background: '#ffffff', border: '1px solid #cbd5e1', borderRadius: 8, color: '#0f172a', fontSize: 12, boxShadow: '0 4px 14px rgba(15,23,42,0.12)' }}
              labelFormatter={(v) => `window ${v}`}
            />
            <ReferenceLine y={0.6} stroke="#eab308" strokeDasharray="4 4" strokeWidth={1.5} />
            <ReferenceLine y={0.75} stroke="#f97316" strokeDasharray="4 4" strokeWidth={1.5} />
            <ReferenceLine y={0.9} stroke="#ef4444" strokeDasharray="4 4" strokeWidth={1.5} />
            <Area type="monotone" dataKey="risk" stroke="#0284c9" strokeWidth={2.5} fill="url(#riskFill)" dot={{ r: 3, fill: '#0284c9', strokeWidth: 0 }} activeDot={{ r: 5 }} isAnimationActive={false} />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
