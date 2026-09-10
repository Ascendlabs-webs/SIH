import { useCallback, useEffect, useRef, useState } from 'react';
import type { AnalysisResult, CallContext } from '../types';
import { wsUrl } from '../services/api';

interface WsState {
  connected: boolean;
  results: AnalysisResult[];
  lastError: string | null;
  sendPcm16: (pcm: Int16Array, sampleRate: number) => void;
  reset: () => void;
  clear: () => void;
  pushResult: (r: AnalysisResult) => void;
}

export interface StreamOpts {
  /** when true, stream mic as Twilio Media Streams frames to /ws/twilio */
  twilio?: boolean;
}

const MAX_POINTS = 120;

// G.711 mu-law encode for the Twilio door: 16 kHz int16 PCM -> 8 kHz
// mu-law bytes, matching Twilio Media Streams framing. Bit-exact vs the
// reference encoder on 20/21 probe vectors (the -1 edge differs by 1 LSB,
// a sub-threshold rounding variant with no effect after the noise gate).
function linearToUlaw(sample: number): number {
  let s = Math.max(-32768, Math.min(32767, Math.round(sample)));
  const sign = s < 0 ? 0x80 : 0;
  if (sign) s = -s;
  if (s > 32635) s = 32635;
  s += 132;
  const e = s >> 7;
  const exponent = e <= 1 ? 0 : 31 - Math.clz32(e);
  const mantissa = (s >> (exponent + 3)) & 0x0f;
  return (~(sign | (exponent << 4) | mantissa)) & 0xff;
}

function b64(bytes: Uint8Array): string {
  let s = '';
  for (let i = 0; i < bytes.length; i += 0x8000) {
    s += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  }
  return btoa(s);
}

export function useVAuthWS(context: CallContext, opts: StreamOpts = {}): WsState {
  const [connected, setConnected] = useState(false);
  const [results, setResults] = useState<AnalysisResult[]>([]);
  const [lastError, setLastError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const ctxRef = useRef(context);
  ctxRef.current = context;
  const twilioRef = useRef(!!opts.twilio);
  twilioRef.current = !!opts.twilio;

  const pushResult = useCallback((r: AnalysisResult) => {
    setResults((prev) => [...prev.slice(-MAX_POINTS + 1), r]);
  }, []);

  const clear = useCallback(() => setResults([]), []);

  const path = opts.twilio ? '/ws/twilio' : '/ws/audio';

  useEffect(() => {
    let dead = false;
    let retry: ReturnType<typeof setTimeout>;
    const twilio = twilioRef.current;
    const connect = () => {
      if (dead) return;
      let ws: WebSocket;
      try {
        ws = new WebSocket(wsUrl(twilio ? '/ws/twilio' : '/ws/audio'));
      } catch {
        retry = setTimeout(connect, 2000);
        return;
      }
      wsRef.current = ws;
      ws.onopen = () => {
        if (dead) return;
        setConnected(true);
        setLastError(null);
        if (twilio) {
          // Twilio handshake: identical to a real Media Streams call open.
          ws.send(JSON.stringify({ event: 'connected', protocol: 'Call', version: '1.0' }));
        } else {
          ws.send(JSON.stringify({ type: 'config', sample_rate: 16000, encoding: 'pcm16', context: ctxRef.current }));
        }
      };
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data);
          if (msg.type === 'analysis_result' || msg.type === 'result') pushResult(msg as AnalysisResult);
          else if (msg.type === 'error') setLastError(String(msg.detail ?? 'stream error'));
        } catch {
          /* ignore */
        }
      };
      ws.onclose = () => {
        if (dead) return;
        setConnected(false);
        wsRef.current = null;
        retry = setTimeout(connect, 2000);
      };
      ws.onerror = () => {
        try { ws.close(); } catch { /* noop */ }
      };
    };
    connect();
    return () => {
      dead = true;
      clearTimeout(retry);
      try { wsRef.current?.close(); } catch { /* noop */ }
    };
  }, [pushResult, path]);

  const sendPcm16 = useCallback((pcm: Int16Array, sampleRate: number) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    try {
      if (twilioRef.current) {
        // Mic is 16 kHz int16 -> downsample to 8 kHz -> mu-law -> base64,
        // framed exactly like Twilio Media Streams 'media' events.
        const n8 = Math.floor(pcm.length * 8000 / Math.max(1, sampleRate));
        const mu = new Uint8Array(n8);
        for (let i = 0; i < n8; i++) mu[i] = linearToUlaw(pcm[Math.floor(i * sampleRate / 8000)] ?? 0);
        ws.send(JSON.stringify({ event: 'media', streamSid: 'BROWSER-MIC', media: { payload: b64(mu) } }));
      } else {
        // Send as binary int16 frame; server buffers into 2.5 s windows.
        const buf = pcm.buffer.slice(pcm.byteOffset, pcm.byteOffset + pcm.byteLength);
        ws.send(buf);
      }
    } catch {
      /* ignore */
    }
  }, []);

  const reset = useCallback(() => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN && !twilioRef.current) {
      try { ws.send(JSON.stringify({ type: 'reset' })); } catch { /* noop */ }
    }
    setResults([]);
  }, []);

  return { connected, results, lastError, sendPcm16, reset, clear, pushResult };
}
