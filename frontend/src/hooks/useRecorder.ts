import { useCallback, useEffect, useRef, useState } from 'react';

export type RecorderStatus = 'idle' | 'recording' | 'paused';

export interface Recording {
  blob: Blob;
  mimeType: string;
  durationMs: number;
}

const MIME_CANDIDATES = ['audio/webm;codecs=opus', 'audio/ogg;codecs=opus', 'audio/mp4', 'audio/webm'];

interface Session {
  recorder: MediaRecorder;
  stream: MediaStream;
  context: AudioContext;
  analyser: AnalyserNode;
  samples: Float32Array<ArrayBuffer>;
  chunks: Blob[];
  accumulatedMs: number;
  resumedAt: number | null;
  timer: number;
}

const elapsedOf = (s: Session) => s.accumulatedMs + (s.resumedAt !== null ? performance.now() - s.resumedAt : 0);

/** Why recording is impossible in this browser context, or null when it works. */
export function recordingUnavailableReason(): string | null {
  if (!window.isSecureContext) return 'Nahrávání mikrofonu vyžaduje HTTPS (nebo localhost).';
  if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
    return 'Tento prohlížeč nepodporuje nahrávání zvuku.';
  }
  return null;
}

/**
 * Microphone recording via MediaRecorder (replaces NAudio WaveInEvent).
 * The VU level is read on demand through `getLevel` so the meter can poll it at animation
 * frame rate without re-rendering the whole app.
 */
export function useRecorder() {
  const [status, setStatus] = useState<RecorderStatus>('idle');
  const [elapsedMs, setElapsedMs] = useState(0);
  const session = useRef<Session | null>(null);

  const release = useCallback(() => {
    const s = session.current;
    if (!s) return;
    window.clearInterval(s.timer);
    s.stream.getTracks().forEach((t) => t.stop());
    void s.context.close().catch(() => undefined);
    session.current = null;
  }, []);

  useEffect(() => release, [release]);

  const start = useCallback(async () => {
    if (session.current) return;
    // Raw signal like the WPF client: no browser-side processing that could hurt recognition.
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: false, noiseSuppression: false, autoGainControl: false },
    });
    try {
      const mimeType = MIME_CANDIDATES.find((m) => MediaRecorder.isTypeSupported(m));
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      const context = new AudioContext();
      const analyser = context.createAnalyser();
      analyser.fftSize = 2048;
      context.createMediaStreamSource(stream).connect(analyser);

      const s: Session = {
        recorder,
        stream,
        context,
        analyser,
        samples: new Float32Array(analyser.fftSize),
        chunks: [],
        accumulatedMs: 0,
        resumedAt: performance.now(),
        timer: 0,
      };
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) s.chunks.push(e.data);
      };
      recorder.start(1000);
      s.timer = window.setInterval(() => setElapsedMs(elapsedOf(s)), 250);
      session.current = s;
      setElapsedMs(0);
      setStatus('recording');
    } catch (error) {
      stream.getTracks().forEach((t) => t.stop());
      throw error;
    }
  }, []);

  const togglePause = useCallback(() => {
    const s = session.current;
    if (!s) return;
    if (s.recorder.state === 'recording') {
      s.recorder.pause();
      s.accumulatedMs = elapsedOf(s);
      s.resumedAt = null;
      setElapsedMs(s.accumulatedMs);
      setStatus('paused');
    } else if (s.recorder.state === 'paused') {
      s.recorder.resume();
      s.resumedAt = performance.now();
      setStatus('recording');
    }
  }, []);

  const stop = useCallback(
    () =>
      new Promise<Recording | null>((resolve) => {
        const s = session.current;
        if (!s) {
          resolve(null);
          return;
        }
        s.recorder.onstop = () => {
          const mimeType = s.recorder.mimeType || s.chunks[0]?.type || 'audio/webm';
          const recording = { blob: new Blob(s.chunks, { type: mimeType }), mimeType, durationMs: elapsedOf(s) };
          release();
          setStatus('idle');
          setElapsedMs(0);
          resolve(recording);
        };
        s.recorder.stop();
      }),
    [release],
  );

  /** Peak level 0..1 of the latest audio frame. */
  const getLevel = useCallback(() => {
    const s = session.current;
    if (!s || s.recorder.state !== 'recording') return 0;
    s.analyser.getFloatTimeDomainData(s.samples);
    let peak = 0;
    for (const v of s.samples) peak = Math.max(peak, Math.abs(v));
    return Math.min(1, peak);
  }, []);

  return { status, elapsedMs, start, togglePause, stop, getLevel };
}
