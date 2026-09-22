import React from 'react';
import type { AlertLevel } from '../types';
import { levelColor, pct } from './helpers';

export function RiskGauge({ risk, level, classification }: { risk: number; level: AlertLevel; classification: string }) {
  const color = levelColor(level);
  const angle = -90 + risk * 180;
  return (
    <div className="gauge-wrap">
      <svg viewBox="0 0 200 112" className="gauge">
        <path d="M 12 100 A 88 88 0 0 1 188 100" fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth="16" strokeLinecap="round" />
        <path
          d="M 12 100 A 88 88 0 0 1 188 100"
          fill="none"
          stroke={color}
          strokeWidth="16"
          strokeLinecap="round"
          strokeDasharray={`${risk * 276.5} 276.5`}
          style={{
            transition: 'stroke-dashoffset 0.4s, stroke 0.4s',
            filter: `drop-shadow(0 0 8px ${color}) drop-shadow(0 0 20px ${color}55)`,
          }}
        />
        <g transform={`rotate(${angle} 100 100)`}>
          <line x1="100" y1="100" x2="100" y2="34" stroke="#00f0ff" strokeWidth="3" strokeLinecap="round" style={{ filter: 'drop-shadow(0 0 4px #00f0ff)' }} />
        </g>
        <circle cx="100" cy="100" r="7" fill="#00f0ff" style={{ filter: 'drop-shadow(0 0 6px #00f0ff)' }} />
      </svg>
      <div className="gauge-risk" style={{ color, textShadow: `0 0 20px ${color}` }}>{pct(risk)}</div>
      <div className="gauge-sub">
        <span className="badge" style={{ background: `${color}22`, color, borderColor: `${color}66`, boxShadow: `0 0 10px ${color}44` }}>{level}</span>
        <span className="cls">{classification === 'SYNTHETIC' ? '⚠ SYNTHETIC VOICE DETECTED' : '● LIKELY GENUINE'}</span>
      </div>
    </div>
  );
}
