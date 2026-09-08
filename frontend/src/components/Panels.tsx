import React from 'react';
import type { AnalysisResult } from '../types';

function row(label: string, value: string) {
  return (
    <div className="metric-row" key={label}>
      <span className="metric-label">{label}</span>
      <span className="metric-value">{value}</span>
    </div>
  );
}

export function TechMetrics({ last }: { last: AnalysisResult | null }) {
  if (!last) return <div className="empty">—</div>;
  const bd = last.latency_breakdown ?? {};
  return (
    <div>
      {row('Analysis window', `${last.window_duration.toFixed(2)} sec`)}
      {row('Processing latency', `${last.latency_ms.toFixed(0)} ms`)}
      {row('· preprocess', `${(bd.preprocess_ms ?? 0).toFixed(1)} ms`)}
      {row('· features', `${(bd.features_ms ?? 0).toFixed(1)} ms`)}
      {row('· inference', `${(bd.inference_ms ?? 0).toFixed(1)} ms`)}
      {row('· risk', `${(bd.risk_ms ?? 0).toFixed(1)} ms`)}
      {row('Audio', `${(last.sample_rate / 1000).toFixed(0)} kHz`)}
      {row('VAD', last.vad_active ? 'ACTIVE' : 'IDLE')}
      {row('Detector', last.detector.toUpperCase())}
      {row('Audio risk', last.audio_risk.toFixed(2))}
      {row('Context adj.', `${last.context_risk >= 0 ? '+' : ''}${last.context_risk.toFixed(2)}`)}
      {row('Protection', last.protection_state)}
    </div>
  );
}

export function SignalAnalysis({ last }: { last: AnalysisResult | null }) {
  if (!last?.features) return <div className="empty">Awaiting analysis windows…</div>;
  const f = last.features;
  const bars: Array<[string, number, string]> = [
    ['MFCC μ₀', Math.min(1, Math.abs(f.mfcc_mean[0] ?? 0) / 400), `${(f.mfcc_mean[0] ?? 0).toFixed(1)}`],
    ['Spectral centroid', Math.min(1, f.spectral_centroid_mean / 6000), `${f.spectral_centroid_mean.toFixed(0)} Hz`],
    ['Spectral flux', Math.min(1, f.spectral_flux_mean / 6), f.spectral_flux_mean.toFixed(2)],
    ['Pitch F₀', Math.min(1, f.f0_mean / 400), `${f.f0_mean.toFixed(0)} Hz ± ${f.f0_std.toFixed(0)}`],
    ['Voice activity', f.vad_active_ratio, `${Math.round(f.vad_active_ratio * 100)}%`],
  ];
  return (
    <div className="sig-list">
      {bars.map(([label, frac, val]) => (
        <div className="sig-row" key={label}>
          <div className="sig-top"><span>{label}</span><span className="sig-val">{val}</span></div>
          <div className="sig-bar"><div className="sig-fill" style={{ width: `${Math.round(frac * 100)}%` }} /></div>
        </div>
      ))}
      <div className="sig-grid">
        <span>ZCR {f.zcr_mean.toFixed(3)}</span>
        <span>RMS {f.rms_mean.toFixed(3)}</span>
        <span>Silence {Math.round(f.silence_ratio * 100)}%</span>
        <span>Rolloff {f.spectral_rolloff_mean.toFixed(0)} Hz</span>
      </div>
    </div>
  );
}

export function EventTimeline({ data }: { data: AnalysisResult[] }) {
  const items = [...data].slice(-8).reverse();
  if (items.length === 0) return <div className="empty">No events yet.</div>;
  return (
    <div className="events">
      {items.map((r, i) => (
        <div className="event" key={`${r.timestamp}-${i}`}>
          <span className={`dot dot-${r.alert_level}`} />
          <span className="event-t">{new Date(r.timestamp).toLocaleTimeString()}</span>
          <span className={`event-l lvl-${r.alert_level}`}>{r.alert_level}</span>
          <span className="event-r">{r.risk_score.toFixed(2)} · {r.classification} · {r.latency_ms.toFixed(0)} ms</span>
        </div>
      ))}
    </div>
  );
}
