import { useEffect, useMemo, useRef, useState } from 'react';
import { analyzeFile, bankUrl, fetchStatus, getModelStatus, getProtection, protectionAction, resetDemo, startDemo } from './services/api';
import { useVAuthWS } from './hooks/useVAuth';
import { useMic } from './hooks/useMic';
import { RiskGauge } from './components/RiskGauge';
import { RiskTimeline } from './components/RiskTimeline';
import { Assistant } from './components/Assistant';
import { EventTimeline, SignalAnalysis, TechMetrics } from './components/Panels';
import { levelColor } from './components/helpers';
import type { AnalysisResult, CallContext, ModelStatus, ProtectionSnapshot, StatusResponse } from './types';
import './index.css';

const DEFAULT_CTX: CallContext = {
  caller_known: false,
  pending_transaction: false,
  sensitive_action: true,
  call_type: 'demo',
};

export default function App() {
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [ctx, setCtx] = useState<CallContext>(DEFAULT_CTX);
  const [mode, setMode] = useState<'DEMO' | 'LIVE'>('DEMO');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [prot, setProt] = useState<ProtectionSnapshot | null>(null);
  const [model, setModel] = useState<ModelStatus | null>(null);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);
  const abortRef = useRef<AbortController | null>(null);

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
    fetchStatus().then(setStatus).catch(() => setStatus(null));
    getModelStatus().then(setModel).catch(() => setModel(null));
    refreshProtection();
    const id = setInterval(() => {
      fetchStatus().then(setStatus).catch(() => undefined);
      getModelStatus().then(setModel).catch(() => undefined);
      refreshProtection();
    }, 5000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => () => { timers.current.forEach(clearTimeout); }, []);

  const last: AnalysisResult | null = results.length ? results[results.length - 1] : null;
  const risk = last?.risk_score ?? 0;
  const level = last?.alert_level ?? 'GREEN';
  const color = levelColor(level);

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
      setNotice(out.message + (slow ? ' Note: placeholder beeps are out-of-distribution for benchmark models — scores reflect the real model, not the demo script.' : ''));
      // Replay windows progressively so the timeline/chart feel live.
      out.results.forEach((r, i) => {
        timers.current.push(setTimeout(() => pushResult(r), 450 * (i + 1)));
      });
      timers.current.push(setTimeout(refreshProtection, 450 * (out.results.length + 1)));
    } catch (e) {
      if (e instanceof DOMException && e.name === 'AbortError') {
        setNotice(ctrl.signal.aborted && Date.now() - t0 >= 180000
          ? 'Analysis timed out after 180 s — the CPU is overloaded. Press Reset and retry.'
          : null);
        return; // superseded run
      }
      setNotice(e instanceof Error ? e.message : 'Demo failed. Is the backend running? Did you generate demo audio?');
    } finally {
      if (abortRef.current === ctrl) abortRef.current = null;
      setBusy(false);
    }
  };

  const onProtect = async (action: 'request_otp' | 'request_callback' | 'mark_verified' | 'escalate') => {
    try {
      const snap = await protectionAction(action);
      setProt(snap);
    } catch (e) {
      setNotice(e instanceof Error ? e.message : 'Protection action failed');
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
      setNotice(`Analysed ${f.name}: ${r.classification} @ ${Math.round(r.risk_score * 100)}% (${r.alert_level}).`);
    } catch (e) {
      setNotice(e instanceof Error ? e.message : 'Upload failed');
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
    } else {
      reset();
      setTwilioLive(false);
      await mic.start();
      setMode('LIVE');
    }
  };

  const toggleTwilioLive = async () => {
    if (twilioLive) {
      stopRecording(false);
      mic.stop();
      setTwilioLive(false);
      setMode('DEMO');
    } else {
      reset();
      setTwilioLive(true);
      await mic.start();
      setMode('LIVE');
      setNotice('Simulated incoming call: your microphone is the caller. Speak and watch VAuth score the call live, exactly as it would score a Twilio phone stream.');
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
      setNotice('Saved my-voice.wav — feed it to scripts/simulate_twilio_call.py --file my-voice.wav to run YOUR voice through the Twilio path.');
    }
  };

  const toggleRecord = async () => {
    if (recording) { stopRecording(true); return; }
    if (!mic.active) { reset(); await mic.start(); setMode('LIVE'); }
    recRef.current = [];
    setRecSecs(0);
    setRecording(true);
    setNotice('Recording your microphone… speak for ~10 s, then stop. It also streams live to the analyzer.');
    const started = Date.now();
    const tickRec = setInterval(() => {
      const s = Math.round((Date.now() - started) / 1000);
      setRecSecs(s);
      if (s >= 15) { clearInterval(tickRec); stopRecording(true); }
    }, 500);
    timers.current.push(tickRec);
  };

  const protState = prot?.state ?? last?.protection_state ?? 'NORMAL';
  const verified = protState === 'VERIFIED';
  const blocked = protState === 'SECONDARY_VERIFICATION_REQUIRED' || protState === 'BLOCKED';

  return (
    <div className="shell">
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
            <button disabled={busy} onClick={() => void playDemo('synthetic')} className="btn synth">{busy ? '⏳ Analyzing…' : '▶ Start Synthetic Voice Demo'}</button>
            <button disabled={busy} onClick={() => void playDemo('real_speech')} className="btn genuine">{busy ? '⏳ Analyzing…' : '▶ Start Real Speech Demo'}</button>
            <button onClick={() => void toggleMic()} className="btn ghost">{mic.active && !twilioLive ? '■ Stop Microphone' : '◉ Use Microphone (Live)'}</button>
            <button onClick={() => void toggleTwilioLive()} className="btn ghost">{twilioLive ? '■ End Simulated Call' : '◉ Simulate Live Call'}</button>
            <button onClick={() => void toggleRecord()} className="btn ghost">{recording ? `■ Stop & save (${recSecs}s)` : '● Record my voice'}</button>
            <label className="btn ghost file">
              ⤒ Upload WAV
              <input type="file" accept=".wav,audio/wav" hidden onChange={(e) => void onUpload(e.target.files?.[0])} />
            </label>
            <button onClick={() => { cancelInflight(); reset(); void resetDemo(); refreshProtection(); setNotice('Session cleared.'); }} className="btn ghost">Reset</button>
          </div>
          {(notice || lastError || mic.error) && (
            <div className="notice">{notice ?? lastError ?? mic.error}</div>
          )}
        </section>

        <section className="card">
          <div className="card-title">Security Recommendation</div>
          <p className="reco">{last?.recommendation ?? 'Awaiting audio — run a demo to see the full pipeline.'}</p>
          <div className="protect">
            <div className="card-title sm">Sensitive Action Protection <span className="hint">backend state: {protState}</span></div>
            <div className="tx">Transaction Request: <strong>₹5,00,000</strong></div>
            <div className={`tx-status ${blocked ? 'blocked' : 'ok'}`}>
              Status: {last ? (verified ? 'VERIFIED — RELEASED' : blocked ? `${protState} — ACTION HELD` : protState === 'ESCALATED' ? 'ESCALATED TO SUPERVISOR' : level === 'GREEN' ? 'ALLOWED' : 'FLAGGED — REVIEW') : '—'}
            </div>
            {(prot?.required_actions ?? last?.protection_actions ?? []).length > 0 && !verified && (
              <div className="req-actions">Required: {(prot?.required_actions ?? last?.protection_actions ?? []).join(' · ')}</div>
            )}
            {(prot?.pending_challenges ?? []).length > 0 && (
              <div className="req-actions">Challenges sent: {prot!.pending_challenges.map((c) => c.channel).join(', ')} (simulated)</div>
            )}
            <div className="controls protect-btns">
              <button className="btn warn" disabled={!last} onClick={() => void onProtect('request_otp')}>Request OTP</button>
              <button className="btn warn" disabled={!last} onClick={() => void onProtect('request_callback')}>Request Callback</button>
              <button className="btn warn" disabled={!last || verified} onClick={() => void onProtect('mark_verified')}>{verified ? '✓ Verified' : 'Mark Verified'}</button>
              <button className="btn ghost" disabled={!last} onClick={() => void onProtect('escalate')}>Escalate</button>
            </div>
          </div>
        </section>

        <section className="card span-wide">
          <div className="card-title">Risk Timeline <span className="hint">thresholds 0.60 / 0.75 / 0.90</span></div>
          <RiskTimeline data={results} />
        </section>

        <section className="card">
          <div className="card-title">Technical Metrics</div>
          <TechMetrics last={last} />
        </section>

        <section className="card">
          <div className="card-title">Signal Analysis</div>
          <SignalAnalysis last={last} />
        </section>

        <section className="card">
          <div className="card-title">Call Information</div>
          <div className="callinfo">
            <label>Call type
              <select value={ctx.call_type} onChange={(e) => setCtx({ ...ctx, call_type: e.target.value as CallContext['call_type'] })}>
                <option value="demo">Demo</option>
                <option value="webrtc">WebRTC</option>
                <option value="twilio">Twilio</option>
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
        </section>

        <section className="card">
          <div className="card-title">Event Timeline</div>
          <EventTimeline data={results} />
        </section>
      </main>

      <footer className="foot">
        VAuth MVP · privacy: raw audio is never stored (STORE_RAW_AUDIO=false) · authorized streams only — uploads, mic, WebRTC, Twilio Media Streams. Cannot intercept ordinary cellular calls.
      </footer>
      <Assistant />
    </div>
  );
}
