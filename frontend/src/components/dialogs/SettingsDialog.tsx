import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import MenuItem from '@mui/material/MenuItem';
import TextField from '@mui/material/TextField';
import { useEffect, useState } from 'react';

import { errorText, fetchLlmModels } from '../../api/client';
import type { UserSettings } from '../../types';

/** Same presets as the WPF SettingsDialogView; models installed in Ollama are added to the list. */
const PRESET_MODELS = ['gemma3:4b', 'gemma3:12b', 'qwen2.5:14b'];

interface Props {
  settings: UserSettings;
  onClose: () => void;
  onSave: (next: UserSettings) => void;
}

/** Rendered only while open, so its state starts fresh from `settings` each time. */
export function SettingsDialog({ settings, onClose, onSave }: Props) {
  const [model, setModel] = useState(settings.ollamaModel);
  const [installed, setInstalled] = useState<string[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    fetchLlmModels()
      .then((r) => {
        if (!active) return;
        setInstalled(r.installed);
        setError(r.error);
      })
      .catch((e) => active && setError(errorText(e)));
    return () => {
      active = false;
    };
  }, []);

  const options = [...new Set([...PRESET_MODELS, ...(installed ?? []), settings.ollamaModel])];

  return (
    <Dialog open onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle>Nastavení</DialogTitle>
      <DialogContent>
        <TextField select fullWidth label="Model Ollama" value={model} onChange={(e) => setModel(e.target.value)} sx={{ mt: 1 }}>
          {options.map((m) => (
            <MenuItem key={m} value={m}>
              {m}
              {installed && !installed.includes(m) ? ' (není stažen)' : ''}
            </MenuItem>
          ))}
        </TextField>
        {error && (
          <Alert severity="warning" sx={{ mt: 2 }}>
            {error}
          </Alert>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Zrušit</Button>
        <Button variant="contained" onClick={() => onSave({ ...settings, ollamaModel: model })}>
          Uložit
        </Button>
      </DialogActions>
    </Dialog>
  );
}
