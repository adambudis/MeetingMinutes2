import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import MenuItem from '@mui/material/MenuItem';
import TextField from '@mui/material/TextField';
import { useEffect, useState } from 'react';

import { fetchTranscriptionModels } from '../../api/client';
import type { Language, TranscriptionModel, UserSettings } from '../../types';

const MODELS: TranscriptionModel[] = ['canary', 'parakeet'];
const LANGUAGES: Language[] = ['cs', 'en'];

interface Props {
  settings: UserSettings;
  onClose: () => void;
  onSave: (next: UserSettings) => void;
}

/** Port of TranscriptionSettingsDialogView: model + language (language only applies to Canary). */
export function TranscriptionSettingsDialog({ settings, onClose, onSave }: Props) {
  const [model, setModel] = useState<TranscriptionModel>(settings.transcriptionModel);
  const [language, setLanguage] = useState<Language>(settings.transcriptionLanguage);
  const [available, setAvailable] = useState<Record<string, boolean> | null>(null);

  useEffect(() => {
    let active = true;
    fetchTranscriptionModels()
      .then((models) => active && setAvailable(Object.fromEntries(models.map((m) => [m.name, m.available]))))
      .catch(() => undefined); // availability hint only
    return () => {
      active = false;
    };
  }, []);

  return (
    <Dialog open onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle>Nastavení přepisu</DialogTitle>
      <DialogContent>
        <TextField
          select
          fullWidth
          label="Model přepisu"
          value={model}
          onChange={(e) => setModel(e.target.value as TranscriptionModel)}
          sx={{ mt: 1 }}
        >
          {MODELS.map((m) => (
            <MenuItem key={m} value={m}>
              {m}
              {available && !available[m] ? ' (model na serveru chybí)' : ''}
            </MenuItem>
          ))}
        </TextField>
        <TextField
          select
          fullWidth
          label="Jazyk (pouze Canary)"
          value={language}
          onChange={(e) => setLanguage(e.target.value as Language)}
          disabled={model !== 'canary'}
          sx={{ mt: 2 }}
        >
          {LANGUAGES.map((l) => (
            <MenuItem key={l} value={l}>
              {l}
            </MenuItem>
          ))}
        </TextField>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Zrušit</Button>
        <Button
          variant="contained"
          onClick={() => onSave({ ...settings, transcriptionModel: model, transcriptionLanguage: language })}
        >
          Uložit
        </Button>
      </DialogActions>
    </Dialog>
  );
}
