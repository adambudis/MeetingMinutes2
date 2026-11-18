import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useState } from 'react';

interface Props {
  labels: string[];
  onConfirm: (names: Record<string, string>) => void;
  onSkip: () => void;
}

/** Port of SpeakerRenameDialogView: map SPEAKER_XX labels to real names (empty = keep label). */
export function SpeakerRenameDialog({ labels, onConfirm, onSkip }: Props) {
  const [names, setNames] = useState<Record<string, string>>({});

  const confirm = () =>
    onConfirm(Object.fromEntries(Object.entries(names).filter(([, name]) => name.trim().length > 0)));

  return (
    <Dialog open onClose={onSkip} maxWidth="xs" fullWidth>
      <DialogTitle>Pojmenování mluvčích</DialogTitle>
      <DialogContent>
        <Box
          component="form"
          onSubmit={(e) => {
            e.preventDefault();
            confirm();
          }}
          sx={{ display: 'grid', gridTemplateColumns: '140px 1fr', alignItems: 'center', rowGap: 1.5, pt: 1 }}
        >
          {labels.map((label, i) => (
            <Box key={label} sx={{ display: 'contents' }}>
              <Typography>{label}</Typography>
              <TextField
                size="small"
                placeholder="Zadej jméno"
                autoFocus={i === 0}
                value={names[label] ?? ''}
                onChange={(e) => setNames((prev) => ({ ...prev, [label]: e.target.value }))}
              />
            </Box>
          ))}
          <button type="submit" hidden />
        </Box>
      </DialogContent>
      <DialogActions>
        <Button onClick={onSkip}>Přeskočit</Button>
        <Button variant="contained" onClick={confirm}>
          OK
        </Button>
      </DialogActions>
    </Dialog>
  );
}
