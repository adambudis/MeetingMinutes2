export interface TranscriptSegment {
  start: number;
  end?: number | null;
  speaker: string;
  text: string;
}

export type ChatRole = 'user' | 'assistant';

export interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  /** Assistant reply still arriving: rendered as plain text, Markdown once finished. */
  streaming: boolean;
  /** Error/cancel placeholder - not sent back to the LLM as conversation history. */
  failed?: boolean;
}

export type TranscriptionModel = 'canary' | 'parakeet';
export type Language = 'cs' | 'en';

export interface UserSettings {
  ollamaModel: string;
  transcriptionModel: TranscriptionModel;
  transcriptionLanguage: Language;
}

/** An audio file waiting to be transcribed (fresh recording or imported file). */
export interface PendingAudio {
  blob: Blob;
  name: string;
  /** First line of the info text shown in the transcript box. */
  header: string;
  /** Object URL for downloading a browser recording. */
  downloadUrl?: string;
}
