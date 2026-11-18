import { describe, expect, it } from 'vitest';

import type { TranscriptSegment } from '../types';
import {
  formatElapsed,
  formatForDisplay,
  formatForLlm,
  formatPendingInfo,
  formatTimestamp,
  recordingFileName,
  renameSpeakers,
  uniqueSpeakers,
} from './transcript';

const segments: TranscriptSegment[] = [
  { start: 3.7, end: 5, speaker: 'SPEAKER_01', text: 'Ahoj.' },
  { start: 65, end: 70, speaker: 'SPEAKER_00', text: 'Začneme.' },
  { start: 3725, end: 3730, speaker: 'SPEAKER_01', text: 'Konec.' },
];

describe('transcript formatting', () => {
  it('formats timestamps', () => {
    expect(formatTimestamp(3.7)).toBe('00:03');
    expect(formatTimestamp(65)).toBe('01:05');
    expect(formatTimestamp(3725)).toBe('1:02:05');
    expect(formatElapsed(75 * 60_000 + 3_400)).toBe('75:03');
  });

  it('renders display and LLM variants', () => {
    expect(formatForDisplay(segments)).toBe('[00:03] SPEAKER_01: Ahoj.\n[01:05] SPEAKER_00: Začneme.\n[1:02:05] SPEAKER_01: Konec.');
    expect(formatForLlm(segments.slice(0, 2))).toBe('SPEAKER_01: Ahoj.\nSPEAKER_00: Začneme.');
  });

  it('lists and renames speakers', () => {
    expect(uniqueSpeakers(segments)).toEqual(['SPEAKER_00', 'SPEAKER_01']);
    const renamed = renameSpeakers(segments, { SPEAKER_01: ' Petr ', SPEAKER_00: '  ' });
    expect(renamed.map((s) => s.speaker)).toEqual(['Petr', 'SPEAKER_00', 'Petr']);
    expect(segments[0].speaker).toBe('SPEAKER_01'); // input untouched
  });

  it('describes the pending transcription', () => {
    const base = { ollamaModel: 'gemma3:12b', transcriptionLanguage: 'en' } as const;
    expect(formatPendingInfo('Importováno: a.mp3', { ...base, transcriptionModel: 'canary' })).toBe(
      'Importováno: a.mp3\nModel: canary | Jazyk: en\n\nNastavení přepisu změníš kliknutím na ⚙ vlevo dole.',
    );
    expect(formatPendingInfo('X', { ...base, transcriptionModel: 'parakeet' })).toContain('\nModel: parakeet\n');
  });

  it('names recordings by date and codec', () => {
    const date = new Date(2026, 10, 5);
    expect(recordingFileName('audio/webm;codecs=opus', date)).toBe('2026-11-05.webm');
    expect(recordingFileName('audio/mp4', date)).toBe('2026-11-05.m4a');
    expect(recordingFileName('', date)).toBe('2026-11-05.webm');
  });
});
