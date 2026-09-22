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
                <stop offset="0%" stopColor="#00f0ff" stopOpacity={0.5} />
                <stop offset="50%" stopColor="#a855f7" stopOpacity={0.25} />
                <stop offset="100%" stopColor="#a855f7" stopOpacity={0.05} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="rgba(255,255,255,0.04)" strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="i" stroke="#94a3b8" tick={{ fontSize: 10 }} tickLine={false} axisLine={{ stroke: 'rgba(255,255,255,0.06)' }} label={{ value: 'window', fill: '#94a3b8', fontSize: 10, position: 'insideBottomRight' }} />
            <YAxis domain={[0, 1]} stroke="#94a3b8" tick={{ fontSize: 10 }} tickLine={false} axisLine={false} width={40} tickFormatter={(v: number) => v.toFixed(2)} />
            <Tooltip
              contentStyle={{
                background: 'rgba(15, 23, 42, 0.95)',
                border: '1px solid rgba(0, 240, 255, 0.25)',
                borderRadius: 12,
                color: '#f1f5f9',
                fontSize: 12,
                backdropFilter: 'blur(10px)',
                boxShadow: '0 0 20px rgba(0, 240, 255, 0.15)',
              }}
              labelFormatter={(v) => `window ${v}`}
            />
            <ReferenceLine y={0.6} stroke="#eab308" strokeDasharray="4 4" strokeWidth={1.5} />
            <ReferenceLine y={0.75} stroke="#f97316" strokeDasharray="4 4" strokeWidth={1.5} />
            <ReferenceLine y={0.9} stroke="#ef4444" strokeDasharray="4 4" strokeWidth={1.5} />
            <Area type="monotone" dataKey="risk" stroke="#00f0ff" strokeWidth={2.5} fill="url(#riskFill)" dot={{ r: 3, fill: '#00f0ff', strokeWidth: 0 }} activeDot={{ r: 5, fill: '#00f0ff', stroke: '#00f0ff', strokeWidth: 2 }} isAnimationActive={false} />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
