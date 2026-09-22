import { useEffect, useMemo, useRef, useState } from 'react';
import { analyzeFile, bankUrl, fetchStatus, getModelStatus, getProtection, getVonageStatus, protectionAction, resetDemo, startDemo } from './services/api';
import { useVAuthWS } from './hooks/useVAuth';
import { useMic } from './hooks/useMic';
import { RiskGauge } from './components/RiskGauge';
import { RiskTimeline } from './components/RiskTimeline';
import { Assistant } from './components/Assistant';
import { EventTimeline, SignalAnalysis, TechMetrics } from './components/Panels';
import { EmptyState } from './components/EmptyState';
import { Skeleton } from './components/Skeleton';
import ParticleBackground from './components/ParticleBackground';
import { useToast } from './components/Toast';
import { useTheme } from './components/Theme';
import { levelColor } from './components/helpers';
import type { AnalysisResult, CallContext, ModelStatus, ProtectionSnapshot, StatusResponse } from './types';
import type { VonageStatus } from './services/api';
import './index.css';

const DEFAULT_CTX: CallContext = {
  caller_known: false,
  pending_transaction: false,
  sensitive_action: true,
  call_type: 'demo',
};

export default function App() {
  const { theme, toggleTheme } = useTheme();
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [ctx, setCtx] = useState<CallContext>(DEFAULT_CTX);
  const [mode, setMode] = useState<'DEMO' | 'LIVE'>('DEMO');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [prot, setProt] = useState<ProtectionSnapshot | null>(null);
  const [model, setModel] = useState<ModelStatus | null>(null);
  const [vonage, setVonage] = useState<VonageStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);
  const abortRef = useRef<AbortController | null>(null);
  const { showToast } = useToast();

  const cancelInflight = () => {
    timers.current.forEach(clearTimeout);
    timers.current = [];
    abortRef.current?.abort();
    abortRef.current = null;
  };

  const refreshProtection = () => {
    getProtection().then(setProt).catch(() => undefined);
  };

  const [twilioLive, setTwilioLive] = useState(false);
  const ctxForStream = useMemo<CallContext>(
    () => ({ ...ctx, call_type: twilioLive ? 'twilio' : mode === 'LIVE' ? 'mic' : 'demo' }),
    [ctx, mode, twilioLive],
  );
  const { connected, results, lastError, sendPcm16, reset, pushResult } = useVAuthWS(ctxForStream, { twilio: twilioLive });
  const recRef = useRef<Int16Array[] | null>(null);
  const [recording, setRecording] = useState(false);
  const [recSecs, setRecSecs] = useState(0);
  const onMicChunk = (pcm: Int16Array, sr: number) => {
    sendPcm16(pcm, sr);
    if (recRef.current) recRef.current.push(new Int16Array(pcm));
  };
  const mic = useMic(onMicChunk);

  useEffect(() => {
    Promise.all([
      fetchStatus().catch(() => null),
      getModelStatus().catch(() => null),
      getVonageStatus().catch(() => null),
    ]).then(([s, m, v]) => {
      setStatus(s);
      setModel(m);
      setVonage(v);
      setLoading(false);
    });
    refreshProtection();
    const id = setInterval(() => {
      fetchStatus().then(setStatus).catch(() => undefined);
      getModelStatus().then(setModel).catch(() => undefined);
      getVonageStatus().then(setVonage).catch(() => undefined);
      refreshProtection();
    }, 5000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => () => { timers.current.forEach(clearTimeout); }, []);

  const last: AnalysisResult | null = results.length ? results[results.length - 1] : null;
  const risk = last?.risk_score ?? 0;
  const level = last?.alert_level ?? 'GREEN';
  const color = levelColor(level);

  // Show toast for high-risk events
  useEffect(() => {
    if (last && last.alert_level === 'RED') {
      showToast('⚠ HIGH RISK: Synthetic voice detected!', 'error');
    }
  }, [last, showToast]);

  const playDemo = async (scenario: 'real' | 'synthetic' | 'real_speech') => {
    cancelInflight();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setBusy(true);
    const modelName = model?.model_name ?? 'detector';
    const slow = model && !model.is_demo;
    const t0 = Date.now();
    setNotice(`Analyzing with ${modelName}… (0s)`);
    const tick = setInterval(() => {
      const s = Math.round((Date.now() - t0) / 1000);
      setNotice(`Analyzing with ${modelName}… (${s}s${slow ? ' — REAL ML takes ~10–25 s on CPU' : ''})`);
    }, 1000);
    timers.current.push(tick);
    const killer = setTimeout(() => ctrl.abort(), 180000);
    timers.current.push(killer);
    try {
      reset();
      await protectionAction('reset').catch(() => undefined);
      const out = await startDemo(scenario, { ...ctx, call_type: 'demo' }, { signal: ctrl.signal });
      clearInterval(tick);
      clearTimeout(killer);
      setMode('DEMO');
      const msg = out.message + (slow ? ' Note: placeholder beeps are out-of-distribution for benchmark models — scores reflect the real model, not the demo script.' : '');
      setNotice(msg);
      showToast(msg, 'info');
      out.results.forEach((r, i) => {
        timers.current.push(setTimeout(() => pushResult(r), 450 * (i + 1)));
      });
      timers.current.push(setTimeout(refreshProtection, 450 * (out.results.length + 1)));
    } catch (e) {
      if (e instanceof DOMException && e.name === 'AbortError') {
        setNotice(ctrl.signal.aborted && Date.now() - t0 >= 180000
          ? 'Analysis timed out after 180 s — the CPU is overloaded. Press Reset and retry.'
          : null);
        return;
      }
      setNotice(e instanceof Error ? e.message : 'Demo failed. Is the backend running? Did you generate demo audio?');
      showToast(e instanceof Error ? e.message : 'Demo failed', 'error');
    } finally {
      if (abortRef.current === ctrl) abortRef.current = null;
      setBusy(false);
    }
  };

  const onProtect = async (action: 'request_otp' | 'request_callback' | 'mark_verified' | 'escalate') => {
    try {
      const snap = await protectionAction(action);
      setProt(snap);
      showToast(`Protection action: ${action}`, 'success');
    } catch (e) {
      setNotice(e instanceof Error ? e.message : 'Protection action failed');
      showToast('Protection action failed', 'error');
    }
  };

  const onUpload = async (f: File | undefined) => {
    if (!f) return;
    setBusy(true);
    setNotice(null);
    try {
      reset();
      const r = await analyzeFile(f, { ...ctx, call_type: 'upload' });
      pushResult(r);
      const msg = `Analysed ${f.name}: ${r.classification} @ ${Math.round(r.risk_score * 100)}% (${r.alert_level}).`;
      setNotice(msg);
      showToast(msg, 'success');
    } catch (e) {
      setNotice(e instanceof Error ? e.message : 'Upload failed');
      showToast(e instanceof Error ? e.message : 'Upload failed', 'error');
    } finally {
      setBusy(false);
    }
  };

  const toggleMic = async () => {
    if (mic.active) {
      stopRecording(false);
      mic.stop();
      setTwilioLive(false);
      setMode('DEMO');
      showToast('Microphone stopped', 'info');
    } else {
      reset();
      setTwilioLive(false);
      await mic.start();
      setMode('LIVE');
      showToast('Microphone started — live analysis active', 'success');
    }
  };

  const toggleTwilioLive = async () => {
    if (twilioLive) {
      stopRecording(false);
      mic.stop();
      setTwilioLive(false);
      setMode('DEMO');
      showToast('Simulated call ended', 'info');
    } else {
      reset();
      setTwilioLive(true);
      await mic.start();
      setMode('LIVE');
      setNotice('Simulated incoming call: your microphone is the caller. Speak and watch VAuth score the call live, exactly as it would score a Twilio phone stream.');
      showToast('Simulated incoming call started', 'warning');
    }
  };

  const downloadWav = (chunks: Int16Array[]) => {
    const total = chunks.reduce((n, c) => n + c.length, 0);
    const data = new Int16Array(total);
    let off = 0;
    for (const c of chunks) { data.set(c, off); off += c.length; }
    const buf = new ArrayBuffer(44 + data.length * 2);
    const v = new DataView(buf);
    const wstr = (o: number, s: string) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
    wstr(0, 'RIFF'); v.setUint32(4, 36 + data.length * 2, true); wstr(8, 'WAVE');
    wstr(12, 'fmt '); v.setUint32(16, 16, true); v.setUint16(20, 1, true);
    v.setUint16(22, 1, true); v.setUint32(24, 16000, true); v.setUint32(28, 32000, true);
    v.setUint16(32, 2, true); v.setUint16(34, 16, true); wstr(36, 'data');
    v.setUint32(40, data.length * 2, true);
    new Int16Array(buf, 44).set(data);
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([buf], { type: 'audio/wav' }));
    a.download = 'my-voice.wav';
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 5000);
  };

  const stopRecording = (download: boolean) => {
    if (!recording) return;
    const chunks = recRef.current ?? [];
    recRef.current = null;
    setRecording(false);
    if (download && chunks.length) {
      downloadWav(chunks);
      showToast('Saved my-voice.wav', 'success');
      setNotice('Saved my-voice.wav — feed it to scripts/simulate_twilio_call.py --file my-voice.wav to run YOUR voice through the Twilio path.');
    }
  };

  const toggleRecord = async () => {
    if (recording) { stopRecording(true); return; }
    if (!mic.active) { reset(); await mic.start(); setMode('LIVE'); }
    recRef.current = [];
    setRecSecs(0);
    setRecording(true);
    showToast('Recording started — speak for ~10s', 'info');
    setNotice('Recording your microphone… speak for ~10 s, then stop. It also streams live to the analyzer.');
    const started = Date.now();
    const tickRec = setInterval(() => {
      const s = Math.round((Date.now() - started) / 1000);
      setRecSecs(s);
      if (s >= 15) { clearInterval(tickRec); stopRecording(true); }
    }, 500);
    timers.current.push(tickRec);
  };

  // Chart export function
  const exportChart = () => {
    const svg = document.querySelector('.chart-box svg');
    if (!svg) {
      showToast('No chart to export yet', 'warning');
      return;
    }
    const serializer = new XMLSerializer();
    const svgString = serializer.serializeToString(svg);
    const blob = new Blob([svgString], { type: 'image/svg+xml' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'vauth-risk-timeline.svg';
    a.click();
    URL.revokeObjectURL(url);
    showToast('Chart exported as SVG', 'success');
  };

  const protState = prot?.state ?? last?.protection_state ?? 'NORMAL';
  const verified = protState === 'VERIFIED';
  const blocked = protState === 'SECONDARY_VERIFICATION_REQUIRED' || protState === 'BLOCKED';

  if (loading) {
    return (
      <div className="shell">
        <div className="scanlines" />
        <header className="topbar">
          <div className="brand">
            <div className="skeleton skeleton-circle" style={{ width: 42, height: 42 }} />
            <div>
              <div className="skeleton skeleton-title" style={{ width: 100, height: 20 }} />
              <div className="skeleton skeleton-text" style={{ width: 150, height: 10 }} />
            </div>
          </div>
          <div className="top-right">
            <Skeleton variant="text" width={120} />
            <Skeleton variant="text" width={100} />
          </div>
        </header>
        <main className="grid">
          <section className="card span-main"><Skeleton variant="card" /></section>
          <section className="card"><Skeleton variant="card" /></section>
          <section className="card span-wide"><Skeleton variant="chart" /></section>
          <section className="card"><Skeleton variant="card" /></section>
          <section className="card"><Skeleton variant="card" /></section>
          <section className="card"><Skeleton variant="card" /></section>
          <section className="card"><Skeleton variant="card" /></section>
        </main>
      </div>
    );
  }

  return (
    <div className="shell">
      <ParticleBackground />
      <div className="scanlines" />
      <header className="topbar">
        <div className="brand">
          <img src="/logo.svg" className="logo-img" alt="VAuth logo" />
          <div>
            <div className="brand-name">VAuth</div>
            <div className="brand-sub">REAL-TIME VOICE AUTHENTICITY</div>
          </div>
        </div>
        <div className="top-right">
          <span className="model-tag" title={model?.model_path ?? ''}>
            MODEL: {model?.model_name ?? '…'} · MODE: {model?.mode_label ?? '…'}
          </span>
          <span className={`conn ${connected ? 'on' : 'off'}`}>● {connected ? 'Connected' : 'Reconnecting…'}</span>
          <span className="mode">{mic.active ? 'LIVE' : mode}</span>
          <button className="theme-toggle" onClick={toggleTheme} title={theme === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}>
            {theme === 'light' ? '🌙' : '☀️'}
          </button>
          <a className="mode bank-link" href={bankUrl()} target="_blank" rel="noreferrer" title="Open the simulated banking demo (separate page)">Demo Bank ↗</a>
        </div>
      </header>

      {model?.warning && (
        <div className="warn-banner">⚠ {model.warning}</div>
      )}

      <main className="grid">
        <section className="card span-main">
          <div className="card-title">Current Risk</div>
          <RiskGauge risk={risk} level={level} classification={last?.classification ?? 'REAL'} />
          <div className="kv">
            <div><span>Alert</span><strong style={{ color }}>{level}</strong></div>
            <div><span>Classification</span><strong>{last?.classification ?? '—'}</strong></div>
            <div><span>Confidence</span><strong>{last ? `${Math.round(last.confidence * 100)}%` : '—'}</strong></div>
          </div>
          <div className="controls">
            <button disabled={busy} onClick={() => void playDemo('synthetic')} className="btn synth ripple">{busy ? '⏳ Analyzing…' : '▶ Start Synthetic Voice Demo'}</button>
            <button disabled={busy} onClick={() => void playDemo('real_speech')} className="btn genuine ripple">{busy ? '⏳ Analyzing…' : '▶ Start Real Speech Demo'}</button>
            <button onClick={() => void toggleMic()} className="btn ghost ripple">{mic.active && !twilioLive ? '■ Stop Microphone' : '◉ Use Microphone (Live)'}</button>
            <button onClick={() => void toggleTwilioLive()} className="btn ghost ripple">{twilioLive ? '■ End Simulated Call' : '◉ Simulate Live Call'}</button>
            <button onClick={() => void toggleRecord()} className={`btn ghost ripple ${recording ? 'recording-pulse' : ''}`}>{recording ? `■ Stop & save (${recSecs}s)` : '● Record my voice'}</button>
            <label className="btn ghost file ripple">
              ⤒ Upload WAV
              <input type="file" accept=".wav,audio/wav" hidden onChange={(e) => void onUpload(e.target.files?.[0])} />
            </label>
            <button onClick={() => { cancelInflight(); reset(); void resetDemo(); refreshProtection(); setNotice('Session cleared.'); showToast('Session cleared', 'info'); }} className="btn ghost ripple">Reset</button>
          </div>
          {(notice || lastError || mic.error) && (
            <div className="notice">{notice ?? lastError ?? mic.error}</div>
          )}
        </section>

        <section className="card">
          <div className="card-title">Security Recommendation</div>
          {last ? (
            <>
              <p className="reco">{last.recommendation}</p>
              <div className="protect">
                <div className="card-title sm">Sensitive Action Protection <span className="hint">backend state: {protState}</span></div>
                <div className="tx">Transaction Request: <strong>₹5,00,000</strong></div>
                <div className={`tx-status ${blocked ? 'blocked' : 'ok'}`}>
                  Status: {verified ? 'VERIFIED — RELEASED' : blocked ? `${protState} — ACTION HELD` : protState === 'ESCALATED' ? 'ESCALATED TO SUPERVISOR' : level === 'GREEN' ? 'ALLOWED' : 'FLAGGED — REVIEW'}
                </div>
                {(prot?.required_actions ?? last.protection_actions ?? []).length > 0 && !verified && (
                  <div className="req-actions">Required: {(prot?.required_actions ?? last.protection_actions ?? []).join(' · ')}</div>
                )}
                {(prot?.pending_challenges ?? []).length > 0 && (
                  <div className="req-actions">Challenges sent: {prot!.pending_challenges.map((c) => c.channel).join(', ')} (simulated)</div>
                )}
                <div className="controls protect-btns">
                  <button className="btn warn ripple" disabled={!last} onClick={() => void onProtect('request_otp')}>Request OTP</button>
                  <button className="btn warn ripple" disabled={!last} onClick={() => void onProtect('request_callback')}>Request Callback</button>
                  <button className="btn warn ripple" disabled={!last || verified} onClick={() => void onProtect('mark_verified')}>{verified ? '✓ Verified' : 'Mark Verified'}</button>
                  <button className="btn ghost ripple" disabled={!last} onClick={() => void onProtect('escalate')}>Escalate</button>
                </div>
              </div>
            </>
          ) : (
            <EmptyState
              icon="🛡️"
              title="No analysis yet"
              message="Run a demo or upload audio to see protection recommendations"
              action={{ label: 'Start Demo', onClick: () => playDemo('real_speech') }}
            />
          )}
        </section>

        <section className="card span-wide">
          <div className="card-title">
            Risk Timeline <span className="hint">thresholds 0.60 / 0.75 / 0.90</span>
          </div>
          {results.length === 0 ? (
            <EmptyState
              icon="📊"
              title="No data yet"
              message="Start a demo or stream audio to see the risk timeline"
              action={{ label: 'Start Demo', onClick: () => playDemo('real_speech') }}
            />
          ) : (
            <>
              <button className="btn ghost export-btn" onClick={exportChart}>⬇ Export SVG</button>
              <RiskTimeline data={results} />
            </>
          )}
        </section>

        <section className="card">
          <div className="card-title">Technical Metrics</div>
          {last ? <TechMetrics last={last} /> : (
            <EmptyState icon="📈" title="No metrics" message="Analysis results will appear here" />
          )}
        </section>

        <section className="card">
          <div className="card-title">Signal Analysis</div>
          {last ? <SignalAnalysis last={last} /> : (
            <EmptyState icon="🎵" title="No signal data" message="Upload audio or run a demo to see features" />
          )}
        </section>

        <section className="card">
          <div className="card-title">Call Information</div>
          <div className="callinfo">
            <label>Call type
              <select value={ctx.call_type} onChange={(e) => setCtx({ ...ctx, call_type: e.target.value as CallContext['call_type'] })}>
                <option value="demo">Demo</option>
                <option value="webrtc">WebRTC</option>
                <option value="twilio">Twilio</option>
                <option value="vonage">Vonage</option>
                <option value="upload">Upload</option>
                <option value="mic">Mic</option>
              </select>
            </label>
            <label className="chk"><input type="checkbox" checked={ctx.caller_known} onChange={(e) => setCtx({ ...ctx, caller_known: e.target.checked })} /> Caller known</label>
            <label className="chk"><input type="checkbox" checked={ctx.pending_transaction} onChange={(e) => setCtx({ ...ctx, pending_transaction: e.target.checked })} /> Pending transaction</label>
            <label className="chk"><input type="checkbox" checked={ctx.sensitive_action} onChange={(e) => setCtx({ ...ctx, sensitive_action: e.target.checked })} /> Sensitive action</label>
          </div>
          <div className="sysline">
            backend {status ? `${status.detector.toUpperCase()} · ${status.window_seconds}s windows · history ${status.history_count}` : '…'}
          </div>
          <div className="sysline">
            Vonage: {vonage == null ? '…' : vonage.configured ? 'CONFIGURED' : vonage.enabled ? 'ENABLED (host missing)' : 'DISABLED'}
          </div>
        </section>

        <section className="card">
          <div className="card-title">Event Timeline</div>
          {results.length === 0 ? (
            <EmptyState icon="📋" title="No events" message="Analysis events will appear here in real-time" />
          ) : (
            <EventTimeline data={results} />
          )}
        </section>
      </main>

      <footer className="foot">
        VAuth MVP · privacy: raw audio is never stored (STORE_RAW_AUDIO=false) · authorized streams only — uploads, mic, WebRTC, Twilio Media Streams. Cannot intercept ordinary cellular calls.
      </footer>
      <Assistant last={last} />
    </div>
  );
}
