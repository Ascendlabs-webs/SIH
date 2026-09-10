import type { AnalysisResult, CallContext, ModelStatus, ProtectionSnapshot, StatusResponse } from '../types';

const JSON_HEADERS = { 'Content-Type': 'application/json' };

// Split-hosting support: set VITE_API_URL (https://<render-app>.onrender.com)
// and VITE_WS_URL (wss://<render-app>.onrender.com) on Vercel. Local dev
// leaves them empty so relative URLs + the Vite proxy apply.
const API_BASE = (import.meta.env.VITE_API_URL as string | undefined ?? '').replace(/\/$/, '');
const WS_BASE = (import.meta.env.VITE_WS_URL as string | undefined ?? '').replace(/\/$/, '');

const api = (path: string) => `${API_BASE}${path}`;

export async function fetchStatus(): Promise<StatusResponse> {
  const r = await fetch(api('/api/status'));
  if (!r.ok) throw new Error(`status ${r.status}`);
  return r.json();
}

export async function fetchHealth(): Promise<{ status: string }> {
  const r = await fetch(api('/health'));
  if (!r.ok) throw new Error(`health ${r.status}`);
  return r.json();
}

export async function fetchHistory(limit = 100): Promise<AnalysisResult[]> {
  const r = await fetch(api(`/api/history?limit=${limit}`));
  if (!r.ok) throw new Error(`history ${r.status}`);
  const j = await r.json();
  return j.results ?? [];
}

export async function startDemo(
  scenario: 'real' | 'synthetic' | 'real_speech',
  context: CallContext,
  opts: { signal?: AbortSignal } = {},
): Promise<{ scenario: string; windows: number; results: AnalysisResult[]; message: string }> {
  const r = await fetch(api('/api/demo/start'), {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ scenario, context }),
    signal: opts.signal,
  });
  if (!r.ok) throw new Error(`demo/start ${r.status}: ${await r.text()}`);
  return r.json();
}

export async function stopDemo(): Promise<void> {
  await fetch(api('/api/demo/stop'), { method: 'POST' });
}

export async function resetDemo(): Promise<void> {
  await fetch(api('/api/demo/reset'), { method: 'POST' });
}

export async function getProtection(): Promise<ProtectionSnapshot> {
  const r = await fetch(api('/api/protection/state'));
  if (!r.ok) throw new Error(`protection ${r.status}`);
  return r.json();
}

export async function getModelStatus(): Promise<ModelStatus> {
  const r = await fetch(api('/api/model/status'));
  if (!r.ok) throw new Error(`model/status ${r.status}`);
  return r.json();
}

export interface VonageStatus {
  enabled: boolean;
  configured: boolean;
  stream_url: string;
  audio_format: string;
}

export async function getVonageStatus(): Promise<VonageStatus | null> {
  try {
    const r = await fetch(api('/api/vonage/config'));
    if (!r.ok) return null;
    return r.json();
  } catch {
    return null;
  }
}

export async function protectionAction(
  action: 'request_otp' | 'request_callback' | 'mark_verified' | 'escalate' | 'reset',
): Promise<ProtectionSnapshot> {
  const r = await fetch(api('/api/protection/action'), {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ action }),
  });
  if (!r.ok) throw new Error(`protection/action ${r.status}: ${await r.text()}`);
  return r.json();
}

export async function analyzeFile(
  file: File,
  context: CallContext,
): Promise<AnalysisResult> {
  const fd = new FormData();
  fd.append('file', file);
  const q = new URLSearchParams({
    caller_known: String(context.caller_known),
    pending_transaction: String(context.pending_transaction),
    sensitive_action: String(context.sensitive_action),
    call_type: context.call_type,
  });
  const r = await fetch(api(`/api/analyze-file?${q.toString()}`), { method: 'POST', body: fd });
  if (!r.ok) throw new Error(`analyze-file ${r.status}: ${await r.text()}`);
  return r.json();
}

export function wsUrl(path: string): string {
  if (WS_BASE) return `${WS_BASE}${path}`;
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  // In dev, vite proxies /ws -> backend; use same host so proxy applies.
  return `${proto}://${window.location.host}${path}`;
}

export async function askAssistant(
  question: string,
  clientState?: { risk_score: number; alert_level: string; classification: string } | null,
): Promise<{ answer: string; context: Record<string, unknown> }> {
  const r = await fetch(api('/api/assistant/ask'), {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ question, client_state: clientState ?? undefined }),
  });
  if (!r.ok) throw new Error(`assistant ${r.status}`);
  return r.json();
}

export function bankUrl(): string {
  return `${API_BASE}/bank`;
}
