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

export function TechMetrics({ last, compact = false }: { last: AnalysisResult | null; compact?: boolean }) {
  if (!last) return <div className="empty">—</div>;
  const bd = last.latency_breakdown ?? {};
  const metrics = compact
    ? [
        ['MFCC µ₀', `${(last.features?.mfcc_mean?.[0] ?? 0).toFixed(1)}`],
        ['Spectral Centroid', `${(last.features?.spectral_centroid_mean ?? 0).toFixed(0)} Hz`],
        ['Spectral Flux', `${(last.features?.spectral_flux_mean ?? 0).toFixed(2)}`],
        ['Pitch F₀', `${(last.features?.f0_mean ?? 0).toFixed(0)} Hz ± ${(last.features?.f0_std ?? 0).toFixed(0)}`],
        ['Voice Activity', `${Math.round((last.features?.vad_active_ratio ?? 0) * 100)}%`],
        ['ZCR', `${(last.features?.zcr_mean ?? 0).toFixed(3)}`],
        ['RMS', `${(last.features?.rms_mean ?? 0).toFixed(3)}`],
        ['Silence', `${Math.round((last.features?.silence_ratio ?? 0) * 100)}%`],
        ['Rolloff', `${(last.features?.spectral_rolloff_mean ?? 0).toFixed(0)} Hz`],
        ['Window', `${last.window_duration.toFixed(2)} sec`],
      ]
    : [
        ['Analysis window', `${last.window_duration.toFixed(2)} sec`],
        ['Processing latency', `${last.latency_ms.toFixed(0)} ms`],
        ['· preprocess', `${(bd.preprocess_ms ?? 0).toFixed(1)} ms`],
        ['· features', `${(bd.features_ms ?? 0).toFixed(1)} ms`],
        ['· inference', `${(bd.inference_ms ?? 0).toFixed(1)} ms`],
        ['· risk', `${(bd.risk_ms ?? 0).toFixed(1)} ms`],
        ['Audio', `${(last.sample_rate / 1000).toFixed(0)} kHz`],
        ['VAD', last.vad_active ? 'ACTIVE' : 'IDLE'],
        ['Detector', last.detector.toUpperCase()],
        ['Audio risk', last.audio_risk.toFixed(2)],
        ['Context adj.', `${last.context_risk >= 0 ? '+' : ''}${last.context_risk.toFixed(2)}`],
        ['Protection', last.protection_state],
      ];

  return (
    <div className={compact ? 'metric-grid' : ''}>
      {metrics.map(([label, value]) => (
        <div className={compact ? 'metric-box' : 'metric-row'} key={label}>
          <span className="metric-label">{label}</span>
          <span className="metric-value">{value}</span>
        </div>
      ))}
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
