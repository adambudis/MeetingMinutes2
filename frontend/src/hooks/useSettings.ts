import { useCallback, useState } from 'react';

import type { Language, TranscriptionModel, UserSettings } from '../types';

const STORAGE_KEY = 'meetingminutes.settings.v1';

export const DEFAULT_SETTINGS: UserSettings = {
  ollamaModel: 'gemma3:12b',
  transcriptionModel: 'canary',
  transcriptionLanguage: 'cs',
};

const MODELS: TranscriptionModel[] = ['canary', 'parakeet'];
const LANGUAGES: Language[] = ['cs', 'en'];

function sanitize(raw: Partial<UserSettings>): UserSettings {
  return {
    ollamaModel:
      typeof raw.ollamaModel === 'string' && raw.ollamaModel.trim() ? raw.ollamaModel : DEFAULT_SETTINGS.ollamaModel,
    transcriptionModel: MODELS.includes(raw.transcriptionModel as TranscriptionModel)
      ? (raw.transcriptionModel as TranscriptionModel)
      : DEFAULT_SETTINGS.transcriptionModel,
    transcriptionLanguage: LANGUAGES.includes(raw.transcriptionLanguage as Language)
      ? (raw.transcriptionLanguage as Language)
      : DEFAULT_SETTINGS.transcriptionLanguage,
  };
}

function load(): UserSettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? sanitize(JSON.parse(raw)) : DEFAULT_SETTINGS;
  } catch {
    return DEFAULT_SETTINGS; // storage blocked or corrupted
  }
}

/** Per-browser user settings (the WPF client kept them in %APPDATA%). */
export function useSettings(): [UserSettings, (next: UserSettings) => void] {
  const [settings, setSettings] = useState<UserSettings>(load);
  const save = useCallback((next: UserSettings) => {
    setSettings(next);
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    } catch {
      // settings still apply for this session
    }
  }, []);
  return [settings, save];
}
