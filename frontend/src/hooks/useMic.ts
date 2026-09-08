import { useCallback, useRef, useState } from 'react';

/** Browser mic -> 16 kHz int16 PCM chunks via AudioContext (optional demo path). */
export function useMic(onChunk: (pcm: Int16Array, sampleRate: number) => void) {
  const [active, setActive] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const nodes = useRef<{ ctx: AudioContext; src: MediaStreamAudioSourceNode; proc: ScriptProcessorNode; stream: MediaStream } | null>(null);
  const cbRef = useRef(onChunk);
  cbRef.current = onChunk;

  const downsample = (input: Float32Array, from: number, to = 16000): Int16Array => {
    if (from === to) {
      const o = new Int16Array(input.length);
      for (let i = 0; i < input.length; i++) o[i] = Math.max(-32768, Math.min(32767, Math.round(input[i] * 32767)));
      return o;
    }
    const ratio = from / to;
    const len = Math.floor(input.length / ratio);
    const o = new Int16Array(len);
    for (let i = 0; i < len; i++) {
      const s = input[Math.floor(i * ratio)] ?? 0;
      o[i] = Math.max(-32768, Math.min(32767, Math.round(s * 32767)));
    }
    return o;
  };

  const start = useCallback(async () => {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
      const Ctx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      const ctx = new Ctx();
      const src = ctx.createMediaStreamSource(stream);
      const proc = ctx.createScriptProcessor(4096, 1, 1);
      proc.onaudioprocess = (ev) => {
        const data = ev.inputBuffer.getChannelData(0);
        const pcm = downsample(new Float32Array(data), ev.inputBuffer.sampleRate, 16000);
        cbRef.current(pcm, 16000);
      };
      src.connect(proc);
      proc.connect(ctx.destination);
      nodes.current = { ctx, src, proc, stream };
      setActive(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Microphone unavailable');
    }
  }, []);

  const stop = useCallback(() => {
    const n = nodes.current;
    if (n) {
      try { n.proc.disconnect(); } catch { /* noop */ }
      try { n.src.disconnect(); } catch { /* noop */ }
      try { n.stream.getTracks().forEach((t) => t.stop()); } catch { /* noop */ }
      try { void n.ctx.close(); } catch { /* noop */ }
    }
    nodes.current = null;
    setActive(false);
  }, []);

  return { active, error, start, stop };
}
