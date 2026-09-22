import type { AlertLevel } from '../types';
import { levelColor, pct } from './helpers';

export function RiskGauge({ risk, level, classification }: { risk: number; level: AlertLevel; classification: string }) {
  const color = levelColor(level);
  const angle = -90 + Math.max(0, Math.min(1, risk)) * 180;
  const genuine = classification !== 'SYNTHETIC';
  const label = genuine ? 'Likely Genuine' : 'Synthetic Voice';
  const pill = level === 'GREEN' ? 'LOW RISK' : level === 'YELLOW' ? 'REVIEW' : level === 'ORANGE' ? 'HIGH RISK' : 'CRITICAL';
  return (
    <div className="gauge-wrap">
      <svg viewBox="0 0 200 118" className="gauge" aria-label={`risk ${pct(risk)}`}>
        <defs>
          <linearGradient id="riskGrad" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#22c55e" />
            <stop offset="38%" stopColor="#eab308" />
            <stop offset="68%" stopColor="#f97316" />
            <stop offset="100%" stopColor="#ef4444" />
          </linearGradient>
        </defs>
        <path d="M 14 102 A 86 86 0 0 1 186 102" fill="none" stroke="#eef2f7" strokeWidth="18" strokeLinecap="round" />
        <path
          d="M 14 102 A 86 86 0 0 1 186 102"
          fill="none"
          stroke="url(#riskGrad)"
          strokeWidth="18"
          strokeLinecap="round"
          strokeDasharray={`${Math.max(0.02, risk) * 270.2} 270.2`}
          style={{ transition: 'stroke-dasharray 0.4s ease' }}
        />
        <g transform={`rotate(${angle} 100 102)`}>
          <line x1="100" y1="102" x2="100" y2="44" stroke="#0f172a" strokeWidth="3.5" strokeLinecap="round" />
        </g>
        <circle cx="100" cy="102" r="6" fill="#0f172a" />
      </svg>
      <div className="gauge-risk" style={{ color: genuine ? '#16a34a' : color }}>{pct(risk)}</div>
      <div className="gauge-label" style={{ color: genuine ? '#16a34a' : color }}>{label}</div>
      <div className="risk-pill">{pill}</div>
    </div>
  );
}
