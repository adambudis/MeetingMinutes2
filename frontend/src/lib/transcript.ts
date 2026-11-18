import type { TranscriptSegment, UserSettings } from '../types';

export const DEFAULT_SUMMARY_PROMPT = 'Vytvoř shrnutí schůzky.';

const pad = (n: number) => String(n).padStart(2, '0');

/** mm:ss, or h:mm:ss for recordings longer than an hour. */
export function formatTimestamp(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  const h = Math.floor(total / 3600);
  const mmss = `${pad(Math.floor((total % 3600) / 60))}:${pad(total % 60)}`;
  return h > 0 ? `${h}:${mmss}` : mmss;
}

/** Recording timer: total minutes, like the WPF client ("75:03"). */
export function formatElapsed(ms: number): string {
  const total = Math.floor(ms / 1000);
  return `${pad(Math.floor(total / 60))}:${pad(total % 60)}`;
}

/** What the transcript box shows: "[mm:ss] Speaker: text" per line. */
export function formatForDisplay(segments: TranscriptSegment[]): string {
  return segments.map((s) => `[${formatTimestamp(s.start)}] ${s.speaker}: ${s.text}`).join('\n');
}

/** What the LLM gets: no timestamps. */
export function formatForLlm(segments: TranscriptSegment[]): string {
  return segments.map((s) => `${s.speaker}: ${s.text}`).join('\n');
}

export function uniqueSpeakers(segments: TranscriptSegment[]): string[] {
  return [...new Set(segments.map((s) => s.speaker))].sort();
}

export function renameSpeakers(segments: TranscriptSegment[], names: Record<string, string>): TranscriptSegment[] {
  return segments.map((s) => {
    const name = names[s.speaker]?.trim();
    return name ? { ...s, speaker: name } : s;
  });
}

/** The info text shown before transcription starts. */
export function formatPendingInfo(header: string, settings: UserSettings): string {
  const modelInfo =
    settings.transcriptionModel === 'canary'
      ? `Model: canary | Jazyk: ${settings.transcriptionLanguage}`
      : `Model: ${settings.transcriptionModel}`;
  return `${header}\n${modelInfo}\n\nNastavení přepisu změníš kliknutím na ⚙ vlevo dole.`;
}

const EXTENSIONS: [string, string][] = [
  ['webm', 'webm'],
  ['ogg', 'ogg'],
  ['mp4', 'm4a'],
  ['mpeg', 'mp3'],
  ['wav', 'wav'],
];

/** "2026-11-15.webm" - date-based name like the WPF save dialog, extension from the recorder MIME type. */
export function recordingFileName(mimeType: string, date: Date = new Date()): string {
  const ext = EXTENSIONS.find(([key]) => mimeType.includes(key))?.[1] ?? 'webm';
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}.${ext}`;
}
