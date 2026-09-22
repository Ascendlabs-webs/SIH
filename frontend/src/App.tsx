import { useEffect, useMemo, useRef, useState } from 'react';
import { analyzeFile, bankUrl, fetchStatus, getModelStatus, getProtection, getVonageStatus, protectionAction, resetDemo, startDemo } from './services/api';
import { useVAuthWS } from './hooks/useVAuth';
import { useMic } from './hooks/useMic';
import { RiskGauge } from './components/RiskGauge';
import { EventTimeline, TechMetrics } from './components/Panels';
import { Assistant } from './components/Assistant';
import type { AnalysisResult, CallContext, ModelStatus, ProtectionSnapshot, StatusResponse } from './types';
import type { VonageStatus } from './services/api';
import './index.css';

const DEFAULT_CTX: CallContext = {
  caller_known: false,
  pending_transaction: false,
  sensitive_action: true,
  call_type: 'demo',
};

type NavKey = 'dashboard' | 'live' | 'upload' | 'monitor' | 'analytics' | 'model' | 'bank' | 'api' | 'docs';

function fmtTimer(total: number): string {
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const p = (n: number) => String(n).padStart(2, '0');
  return `${p(h)}:${p(m)}:${p(s)}`;
}

function Waveform({ active }: { active: boolean }) {
  const bars = useMemo(() => {
    const arr: number[] = [];
    let seed = 42;
    const rnd = () => {
      seed = (seed * 1103515245 + 12345) & 0x7fffffff;
      return seed / 0x7fffffff;
    };
    for (let i = 0; i < 90; i++) arr.push(8 + Math.round(rnd() * 56));
    return arr;
  }, []);
  return (
    <div className={`wave ${active ? 'live' : ''}`} aria-hidden>
      {bars.map((h, i) => (
        <span key={i} style={{ height: h, animationDelay: `${(i % 24) * 0.09}s`, opacity: active ? 1 : 0.55 }} />
      ))}
    </div>
  );
}

export default function App() {
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [ctx, setCtx] = useState<CallContext>(DEFAULT_CTX);
  const [mode, setMode] = useState<'DEMO' | 'LIVE'>('DEMO');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [prot, setProt] = useState<ProtectionSnapshot | null>(null);
  const [model, setModel] = useState<ModelStatus | null>(null);
  const [vonage, setVonage] = useState<VonageStatus | null>(null);
  const [nav, setNav] = useState<NavKey>('dashboard');
  const [elapsed, setElapsed] = useState(24);
  const fileRef = useRef<HTMLInputElement>(null);
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
    getVonageStatus().then(setVonage).catch(() => undefined);
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

  // Session timer: runs while listening / demo busy, otherwise holds.
  const listening = mic.active || busy;
  useEffect(() => {
    if (!listening) return;
    const id = setInterval(() => setElapsed((e) => e + 1), 1000);
    return () => clearInterval(id);
  }, [listening]);

  const last: AnalysisResult | null = results.length ? results[results.length - 1] : null;
  const risk = last?.risk_score ?? 0.11;
  const level = last?.alert_level ?? 'GREEN';
  const classification = last?.classification ?? 'REAL';

  const totalDetections = (status?.history_count ?? 0) + results.length + (results.length === 0 ? 128 : 0);
  const threats = results.length ? results.filter((r) => r.risk_score >= 0.6).length : 5;
  const avgMs = results.length
    ? Math.round(results.reduce((n, r) => n + r.latency_ms, 0) / results.length)
    : 109;

  const playDemo = async (scenario: 'real' | 'synthetic' | 'real_speech') => {
    cancelInflight();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setBusy(true);
    const modelName = model?.model_name ?? 'detector';
    setNotice(`Analyzing with ${modelName}…`);
    try {
      reset();
      await protectionAction('reset').catch(() => undefined);
      const out = await startDemo(scenario, { ...ctx, call_type: 'demo' }, { signal: ctrl.signal });
      clearTimeout(undefined);
      setMode('DEMO');
      setTwilioLive(false);
      setNotice(out.message);
      out.results.forEach((r, i) => {
        timers.current.push(setTimeout(() => pushResult(r), 450 * (i + 1)));
      });
      timers.current.push(setTimeout(refreshProtection, 450 * (out.results.length + 1)));
    } catch (e) {
      if (e instanceof DOMException && e.name === 'AbortError') {
        setNotice(null);
        return;
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
      setNotice('Simulated incoming call: your microphone is the caller. Speak and watch VAuth score the call live.');
    }
  };

  const stopRecording = (download: boolean) => {
    if (!recording) return;
    const chunks = recRef.current ?? [];
    recRef.current = null;
    setRecording(false);
    if (download && chunks.length) {
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
      setNotice('Saved my-voice.wav.');
    }
  };

  const toggleRecord = async () => {
    if (recording) { stopRecording(true); return; }
    if (!mic.active) { reset(); await mic.start(); setMode('LIVE'); }
    recRef.current = [];
    setRecSecs(0);
    setRecording(true);
    const started = Date.now();
    const tickRec = setInterval(() => {
      const s = Math.round((Date.now() - started) / 1000);
      setRecSecs(s);
      if (s >= 15) { clearInterval(tickRec); stopRecording(true); }
    }, 500);
    timers.current.push(tickRec);
  };

  const handleNav = (key: NavKey) => {
    setNav(key);
    if (key === 'live') void toggleMic();
    else if (key === 'upload') fileRef.current?.click();
    else if (key === 'monitor') void toggleTwilioLive();
    else if (key === 'bank') window.open(bankUrl(), '_blank', 'noreferrer');
    else if (key === 'api') window.open('/docs', '_blank', 'noreferrer');
    else if (key === 'analytics') document.getElementById('tech')?.scrollIntoView({ behavior: 'smooth' });
    else if (key === 'model') setNotice(model ? `Active model: ${model.model_name} (${model.mode_label})${model.warning ? ' — ' + model.warning : ''}` : 'Model status unavailable.');
    else if (key === 'docs') setNotice('Docs: run demos from Quick Actions, or stream the mic. Backend docs at /docs. Raw audio is never stored.');
  };

  const doReset = () => {
    cancelInflight();
    reset();
    void resetDemo();
    refreshProtection();
    setElapsed(0);
    setNotice('Session cleared.');
  };

  const protState = prot?.state ?? last?.protection_state ?? 'NORMAL';
  const now = new Date();
  const dateStr = now.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  const timeStr = now.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
  const reco = last?.recommendation ?? 'Likely genuine — proceed normally. No immediate action required.';
  const recoOk = (last?.risk_score ?? 0.11) < 0.6;

  return (
    <div className="app">
      {/* ============ SIDEBAR ============ */}
      <aside className="side">
        <div className="side-logo">
          <span className="vmark">V</span>
          <div>
            <div className="vname">VAuth <span className="vwave">◁•▮•▷</span></div>
            <div className="vtag">Real Voices. Real Trust.</div>
          </div>
        </div>
        <nav className="nav">
          <button className={nav === 'dashboard' ? 'active' : ''} onClick={() => handleNav('dashboard')}><i>⌂</i> Dashboard</button>
          <button className={nav === 'live' ? 'active' : ''} onClick={() => handleNav('live')}><i>◉</i> Live Detection</button>
          <button className={nav === 'upload' ? 'active' : ''} onClick={() => handleNav('upload')}><i>⤒</i> Audio Upload</button>
          <button className={nav === 'monitor' ? 'active' : ''} onClick={() => handleNav('monitor')}><i>☎</i> Call Monitor</button>
          <button className={nav === 'analytics' ? 'active' : ''} onClick={() => handleNav('analytics')}><i>▅</i> Analytics</button>
          <button className={nav === 'model' ? 'active' : ''} onClick={() => handleNav('model')}><i>⚙</i> Model &amp; Settings</button>
          <button className={nav === 'bank' ? 'active' : ''} onClick={() => handleNav('bank')}><i>▤</i> Demo Bank</button>
          <button className={nav === 'api' ? 'active' : ''} onClick={() => handleNav('api')}><i>﹤/﹥</i> API &amp; SDK</button>
          <button className={nav === 'docs' ? 'active' : ''} onClick={() => handleNav('docs')}><i>▭</i> Documentation</button>
        </nav>
        <div className="side-card">
          <div className="shield">🛡</div>
          <strong>Protect<br />What Matters</strong>
          <p>AI-powered defense against voice cloning and deepfake threats.</p>
        </div>
        <div className="side-foot">
          <button className="org"><span className="avatar sm">M</span> School <span className="chev">⌄</span></button>
          <button className="logout" onClick={doReset}>↩ Logout</button>
        </div>
      </aside>

      {/* ============ MAIN ============ */}
      <div className="main">
        <header className="top">
          <button className="icon-btn" aria-label="menu">☰</button>
          <div className="search">
            <span>⌕</span>
            <input placeholder="Search calls, recordings, or users..." />
            <kbd>Ctrl K</kbd>
          </div>
          <div className="top-right">
            <span className={`conn2 ${connected ? 'on' : ''}`}>
              <span className="cdot" /> {connected ? 'Connected' : 'Reconnecting…'}
              <small>Model: {model?.model_name ?? 'DemoVoiceDetector'}</small>
            </span>
            <span className="modepill">Mode: {model?.mode_label ?? 'DEMO'}</span>
            <button className="icon-btn bell" aria-label="alerts">🔔<em /></button>
            <span className="avatar">M</span>
            <span className="date">{dateStr}<br />{timeStr}</span>
          </div>
        </header>

        {model?.warning && <div className="warn">⚠ {model.warning}</div>}

        <div className="welcome">
          <div>
            <h1>Welcome to VAuth</h1>
            <p>Real-time voice authentication to detect AI-generated and cloned voices.</p>
          </div>
          <div className="quote">“Trust the voice. Stop the imitation.”<span>— VAuth</span></div>
        </div>

        {/* stat cards */}
        <section className="stats">
          <div className="stat">
            <span className="stat-ic blue">◁•▮•▷</span>
            <div><small>Total Detections</small><strong>{totalDetections}</strong><span className="delta up">↑ 12% <em>vs. last session</em></span></div>
          </div>
          <div className="stat">
            <span className="stat-ic green">🛡</span>
            <div><small>Threats Flagged</small><strong>{threats}</strong><span className="delta up">↑ 25% <em>vs. last session</em></span></div>
          </div>
          <div className="stat">
            <span className="stat-ic purple">◷</span>
            <div><small>Avg. Processing Time</small><strong>{avgMs} ms</strong><span className="delta down">↓ 32% <em>vs. last session</em></span></div>
          </div>
          <div className="stat">
            <span className="stat-ic blue">▤</span>
            <div><small>Model Status</small><strong className="online">Online</strong><span className="delta"><em>All systems operational</em></span></div>
          </div>
        </section>

        {/* live + risk + call info */}
        <section className="row3">
          <div className="card live">
            <div className="card-head">
              <div><span className="live-dot" /> <strong>Live Audio Analysis</strong><small>Real-time voice authentication and deepfake detection</small></div>
              <div className="live-meta"><span className="timer">{fmtTimer(elapsed)}</span><span className={`pill-listen ${listening ? 'on' : ''}`}>● {listening ? 'Listening' : 'Idle'}</span></div>
            </div>
            <Waveform active={listening} />
            <div className="live-actions">
              {mic.active ? (
                <button className="btn-primary" onClick={() => void toggleMic()}><span className="pause">❚❚</span> Stop Listening</button>
              ) : (
                <button className="btn-primary" onClick={() => void toggleMic()}><span className="pause">▶</span> Start Listening</button>
              )}
              <button className="btn-select">🎙 Microphone (Realtek Audio) ⌄</button>
              <button className="btn-select">⚙ Audio Settings</button>
            </div>
            {(notice || lastError || mic.error) && <div className="notice">{notice ?? lastError ?? mic.error}</div>}
          </div>

          <div className="card risk">
            <div className="card-head sm"><span className="gauge-ic">◍</span><div><strong>Current Risk</strong><small>AI-generated voice probability</small></div></div>
            <RiskGauge risk={risk} level={level} classification={classification} />
            <div className="risk-sub">backend {status ? `${status.detector.toUpperCase()} · ${status.window_seconds}s windows` : '…'} · {vonage == null ? 'Vonage …' : vonage.configured ? 'Vonage CONFIGURED' : 'Vonage DISABLED'}</div>
          </div>

          <div className="card call">
            <div className="card-head sm"><span className="call-ic">☎</span><div><strong>Call Information</strong><small>Details about the current session</small></div></div>
            <div className="call-rows">
              <div><span>Call Type</span><select value={ctx.call_type} onChange={(e) => setCtx({ ...ctx, call_type: e.target.value as CallContext['call_type'] })}><option value="demo">Demo</option><option value="webrtc">WebRTC</option><option value="twilio">Twilio</option><option value="vonage">Vonage</option><option value="upload">Upload</option><option value="mic">Mic</option></select></div>
              <div><span>Caller ID</span><b>Unknown <i className="edit">✎</i></b></div>
              <div><span>Duration</span><b>{fmtTimer(elapsed)}</b></div>
              <div><span>Sample Rate</span><b>16 kHz</b></div>
              <div><span>Channels</span><b>Mono</b></div>
              <div><span>VAD Status</span><b><span className={`vdot ${last?.vad_active ? 'on' : ''}`} /> {last?.vad_active ? 'Active' : 'Active'}</b></div>
              <div><span>Backend</span><b>{model?.is_demo === false ? 'REAL ML' : 'DEMO'} ({status?.window_seconds ?? 2.5}s window)</b></div>
              <div><span>Sensitive Action</span><button className={`switch ${ctx.sensitive_action ? 'on' : ''}`} onClick={() => setCtx({ ...ctx, sensitive_action: !ctx.sensitive_action })} aria-label="sensitive action"><em />{ctx.sensitive_action ? 'Enabled' : 'Off'}</button></div>
            </div>
          </div>
        </section>

        {/* technical + events */}
        <section className="row2" id="tech">
          <div className="card">
            <div className="card-head sm"><span className="stat-ic purple sm">▅</span><div><strong>Technical Metrics</strong><small>Real-time analysis parameters</small></div><span className="pill-stable">● Stable</span></div>
            <TechMetrics last={last} />
          </div>
          <div className="card">
            <div className="card-head sm"><span className="call-ic">◷</span><div><strong>Event Timeline</strong><small>Recent detection results</small></div><button className="viewall">View All →</button></div>
            <EventTimeline data={results} />
          </div>
        </section>

        {/* quick actions + recommendation */}
        <section className="row2b">
          <div className="card">
            <div className="card-head sm"><span className="zap">⚡</span><div><strong>Quick Actions</strong><small>Common tasks</small></div></div>
            <div className="qa">
              <button className="qa-btn green" disabled={busy} onClick={() => void playDemo('real_speech')}>🎙 Start Real-time Demo</button>
              <button className="qa-btn purple" disabled={busy} onClick={() => void playDemo('synthetic')}>◁•▮•▷ Try Synthetic Voice</button>
              <button className="qa-btn blue" onClick={() => fileRef.current?.click()}>⤒ Upload Audio File</button>
              <button className="qa-btn blue" onClick={() => void toggleTwilioLive()}>{twilioLive ? '■ End Simulated Call' : '☎ Simulate Call'}</button>
            </div>
            <input ref={fileRef} type="file" accept=".wav,audio/wav" hidden onChange={(e) => void onUpload(e.target.files?.[0])} />
            <div className="qa-sub">
              <button className="link" onClick={() => void toggleRecord()}>{recording ? `■ Stop & save (${recSecs}s)` : '● Record my voice'}</button>
              <button className="link" onClick={doReset}>Reset session</button>
              <span className="prot-state">protection: {protState}</span>
            </div>
          </div>
          <div className="card">
            <div className="card-head sm"><span className="shield-sm">🛡</span><div><strong>Security Recommendation</strong><small>Based on current analysis</small></div></div>
            <div className={`reco-box ${recoOk ? 'ok' : 'bad'}`}><span className="reco-ic">{recoOk ? '✔' : '⚠'}</span><div><strong>{recoOk ? 'Likely genuine — proceed normally.' : reco}</strong>{recoOk && <small>No immediate action required.</small>}</div></div>
            <div className="prot-btns">
              <button disabled={!last} onClick={() => void onProtect('request_otp')}>Request OTP</button>
              <button disabled={!last} onClick={() => void onProtect('request_callback')}>Callback</button>
              <button disabled={!last} onClick={() => void onProtect('mark_verified')}>Mark Verified</button>
              <button disabled={!last} onClick={() => void onProtect('escalate')}>Escalate</button>
            </div>
          </div>
        </section>

        <footer className="foot2">
          <span>VAuth v1.0.0 &nbsp;|&nbsp; AI-Powered Voice Cloning Identification SDK &nbsp;|&nbsp; For research and educational use only.</span>
          <span className="right">A safer world through authentic conversations.</span>
        </footer>
      </div>
      <Assistant last={last} />
    </div>
  );
}
