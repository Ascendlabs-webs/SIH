import type { AnalysisResult } from '../types';

function fmtClock(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString('en-US', { hour12: false });
  } catch {
    return '--:--:--';
  }
}

export function TechMetrics({ last }: { last: AnalysisResult | null }) {
  if (!last) {
    return (
      <div className="tech-grid">
        {['MFCC μ₀', 'Spectral Centroid', 'Spectral Flux', 'Pitch F₀', 'Voice Activity', 'ZCR', 'RMS', 'Silence Ratio', 'Rolloff Frequency', 'Analysis Window'].map((l) => (
          <div className="tech-cell" key={l}>
            <div className="tech-label">{l}</div>
            <div className="tech-value dim">—</div>
          </div>
        ))}
      </div>
    );
  }
  const f = last.features;
  const cells: Array<[string, string]> = [
    ['MFCC μ₀', f ? (f.mfcc_mean[0] ?? 0).toFixed(1) : '—'],
    ['Spectral Centroid', f ? `${f.spectral_centroid_mean.toFixed(0)} Hz` : '—'],
    ['Spectral Flux', f ? f.spectral_flux_mean.toFixed(2) : '—'],
    ['Pitch F₀', f ? `${f.f0_mean.toFixed(0)} Hz ± ${f.f0_std.toFixed(0)}` : '—'],
    ['Voice Activity', f ? `${Math.round(f.vad_active_ratio * 100)}%` : '—'],
    ['ZCR', f ? f.zcr_mean.toFixed(3) : '—'],
    ['RMS', f ? f.rms_mean.toFixed(3) : '—'],
    ['Silence Ratio', f ? `${Math.round(f.silence_ratio * 100)}%` : '—'],
    ['Rolloff Frequency', f ? `${f.spectral_rolloff_mean.toFixed(0)} Hz` : '—'],
    ['Analysis Window', `${last.window_duration.toFixed(2)} sec`],
  ];
  return (
    <div className="tech-grid">
      {cells.map(([label, value]) => (
        <div className="tech-cell" key={label}>
          <div className="tech-label">{label}</div>
          <div className="tech-value">{value}</div>
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
  const items = [...data].slice(-5).reverse();
  if (items.length === 0) return <div className="empty">No events yet — run a demo or stream the mic.</div>;
  return (
    <div className="events-clean">
      {items.map((r, i) => {
        const bad = r.risk_score >= 0.6;
        return (
          <div className="event-clean" key={`${r.timestamp}-${i}`}>
            <span className={`edot ${bad ? 'bad' : 'good'}`} />
            <span className="etime">{fmtClock(r.timestamp)}</span>
            <span className={`elabel ${bad ? 'bad' : ''}`}>{bad ? 'Suspicious pattern' : 'Genuine voice detected'}</span>
            <span className={`escore ${bad ? 'bad' : ''}`}>{r.risk_score.toFixed(2)}</span>
            <span className="ems">{r.latency_ms.toFixed(0)} ms</span>
          </div>
        );
      })}
    </div>
  );
}
