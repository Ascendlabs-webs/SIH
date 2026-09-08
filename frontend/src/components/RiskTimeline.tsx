import React from 'react';
import {
  CartesianGrid,
  Line,
  LineChart,
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
          <LineChart data={pts} margin={{ top: 8, right: 12, bottom: 0, left: -18 }}>
            <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" />
            <XAxis dataKey="i" stroke="#64748b" tick={{ fontSize: 11 }} label={{ value: 'window', fill: '#64748b', fontSize: 11, position: 'insideBottomRight' }} />
            <YAxis domain={[0, 1]} stroke="#64748b" tick={{ fontSize: 11 }} />
            <Tooltip
              contentStyle={{ background: '#ffffff', border: '1px solid #cbd5e1', color: '#0f172a', fontSize: 12 }}
              labelFormatter={(v) => `window ${v}`}
            />
            <ReferenceLine y={0.6} stroke="#eab308" strokeDasharray="4 4" />
            <ReferenceLine y={0.75} stroke="#f97316" strokeDasharray="4 4" />
            <ReferenceLine y={0.9} stroke="#ef4444" strokeDasharray="4 4" />
            <Line type="monotone" dataKey="risk" stroke="#38bdf8" strokeWidth={2} dot={{ r: 2, fill: '#38bdf8' }} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
