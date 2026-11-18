import type { Language, TranscriptionModel, TranscriptSegment } from '../types';
import { SseParser } from './sse';

export type SummaryEvent =
  | { event: 'warning'; data: { message: string } }
  | { event: 'chunk'; data: { current: number; total: number } }
  | { event: 'token'; data: { text: string } }
  | { event: 'done'; data: { markdown: string; map_success_ratio: number } }
  | { event: 'error'; data: { message: string } };

export type ChatEvent =
  | { event: 'token'; data: { text: string } }
  | { event: 'done'; data: { text: string } }
  | { event: 'error'; data: { message: string } };

export interface ChatRequestMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface LlmModels {
  default: string;
  installed: string[];
  error: string | null;
}

export interface TranscriptionModelInfo {
  name: TranscriptionModel;
  available: boolean;
  languages: Language[];
}

export function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError';
}

export function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function statusMessage(status: number): string {
  if (status === 413) return 'Soubor je příliš velký.';
  if (status === 502 || status === 503 || status === 504) return `Server je nedostupný (HTTP ${status}).`;
  return `Požadavek selhal (HTTP ${status}).`;
}

/** Extract FastAPI's `detail` (string or validation list) from an error body. */
export function messageFromBody(body: string, status: number): string {
  try {
    const detail: unknown = JSON.parse(body)?.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
      const parts = detail.map((d) => (d && typeof d === 'object' && 'msg' in d ? String(d.msg) : '')).filter(Boolean);
      if (parts.length) return parts.join('; ');
    }
  } catch {
    // not JSON (e.g. an nginx error page)
  }
  return statusMessage(status);
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) throw new Error(messageFromBody(await res.text(), res.status));
  return (await res.json()) as T;
}

export const fetchLlmModels = () => getJson<LlmModels>('/api/llm/models');

export const fetchTranscriptionModels = () =>
  getJson<{ models: TranscriptionModelInfo[] }>('/api/transcribe/models').then((r) => r.models);

async function* postSse(path: string, body: unknown, signal: AbortSignal): AsyncGenerator<{ event: string; data: unknown }> {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok || !res.body) throw new Error(messageFromBody(await res.text(), res.status));

  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  const parser = new SseParser();
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) return;
      for (const message of parser.feed(value)) {
        yield { event: message.event, data: JSON.parse(message.data) };
      }
    }
  } finally {
    reader.releaseLock();
  }
}

export function summarize(
  request: { transcript: string; model: string; segments: TranscriptSegment[] | null },
  signal: AbortSignal,
): AsyncGenerator<SummaryEvent> {
  return postSse('/api/summarize', request, signal) as AsyncGenerator<SummaryEvent>;
}

export function chat(
  request: { messages: ChatRequestMessage[]; model: string },
  signal: AbortSignal,
): AsyncGenerator<ChatEvent> {
  return postSse('/api/chat', request, signal) as AsyncGenerator<ChatEvent>;
}

export interface TranscribeOptions {
  file: Blob;
  fileName: string;
  model: TranscriptionModel;
  language: Language;
  onUploadProgress?: (fraction: number) => void;
  onProgress?: (message: string) => void;
  signal?: AbortSignal;
}

/**
 * Upload a recording and follow the transcription progress stream. Uses XMLHttpRequest
 * because fetch cannot report upload progress, which matters for long recordings.
 */
export function transcribe(options: TranscribeOptions): Promise<TranscriptSegment[]> {
  const { file, fileName, model, language, onUploadProgress, onProgress, signal } = options;

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const parser = new SseParser();
    let consumed = 0;
    let segments: TranscriptSegment[] | null = null;
    let failure: string | null = null;

    const consume = () => {
      const text = xhr.responseText;
      const chunk = text.slice(consumed);
      consumed = text.length;
      for (const message of parser.feed(chunk)) {
        const data = JSON.parse(message.data);
        if (message.event === 'progress') onProgress?.(data.message);
        else if (message.event === 'result') segments = data.segments;
        else if (message.event === 'error') failure = data.message;
      }
    };

    xhr.open('POST', '/api/transcribe');
    xhr.setRequestHeader('Accept', 'text/event-stream');
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onUploadProgress?.(e.loaded / e.total);
    };
    xhr.onprogress = () => {
      if (xhr.status === 200) consume();
    };
    xhr.onload = () => {
      if (xhr.status !== 200) {
        reject(new Error(messageFromBody(xhr.responseText, xhr.status)));
        return;
      }
      consume();
      if (failure) reject(new Error(failure));
      else if (segments) resolve(segments);
      else reject(new Error('Spojení se serverem bylo přerušeno před dokončením přepisu.'));
    };
    xhr.onerror = () => reject(new Error('Chyba sítě - server je nedostupný.'));
    xhr.onabort = () => reject(new DOMException('Přepis zrušen', 'AbortError'));
    signal?.addEventListener('abort', () => xhr.abort(), { once: true });

    const form = new FormData();
    form.append('file', file, fileName);
    form.append('model', model);
    form.append('language', language);
    xhr.send(form);
  });
}
