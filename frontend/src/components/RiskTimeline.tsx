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
                <stop offset="0%" stopColor="#0ea5e9" stopOpacity={0.3} />
                <stop offset="50%" stopColor="#8b5cf6" stopOpacity={0.15} />
                <stop offset="100%" stopColor="#ec4899" stopOpacity={0.05} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="rgba(0,0,0,0.04)" strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="i" stroke="#64748b" tick={{ fontSize: 10 }} tickLine={false} axisLine={{ stroke: 'rgba(0,0,0,0.06)' }} label={{ value: 'window', fill: '#64748b', fontSize: 10, position: 'insideBottomRight' }} />
            <YAxis domain={[0, 1]} stroke="#64748b" tick={{ fontSize: 10 }} tickLine={false} axisLine={false} width={40} tickFormatter={(v: number) => v.toFixed(2)} />
            <Tooltip
              contentStyle={{
                background: 'rgba(255, 255, 255, 0.95)',
                border: '1px solid rgba(14, 165, 233, 0.2)',
                borderRadius: 12,
                color: '#0f172a',
                fontSize: 12,
                backdropFilter: 'blur(10px)',
                boxShadow: '0 4px 15px rgba(0, 0, 0, 0.06)',
              }}
              labelFormatter={(v) => `window ${v}`}
            />
            <ReferenceLine y={0.6} stroke="#eab308" strokeDasharray="4 4" strokeWidth={1.5} />
            <ReferenceLine y={0.75} stroke="#f97316" strokeDasharray="4 4" strokeWidth={1.5} />
            <ReferenceLine y={0.9} stroke="#ef4444" strokeDasharray="4 4" strokeWidth={1.5} />
            <Area type="monotone" dataKey="risk" stroke="#0ea5e9" strokeWidth={2.5} fill="url(#riskFill)" dot={{ r: 3, fill: '#0ea5e9', strokeWidth: 0 }} activeDot={{ r: 5, fill: '#0ea5e9', stroke: '#0ea5e9', strokeWidth: 2 }} isAnimationActive={false} />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
