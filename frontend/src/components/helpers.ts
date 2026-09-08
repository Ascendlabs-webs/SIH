import type { AlertLevel } from '../types';

export const LEVEL_COLOR: Record<AlertLevel, string> = {
  GREEN: '#22c55e',
  YELLOW: '#eab308',
  ORANGE: '#f97316',
  RED: '#ef4444',
};

export function levelColor(level: AlertLevel): string {
  return LEVEL_COLOR[level] ?? '#94a3b8';
}

export function pct(risk: number): string {
  return `${Math.round(risk * 100)}%`;
}
