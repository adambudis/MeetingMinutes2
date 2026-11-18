import DownloadIcon from '@mui/icons-material/Download';
import MicIcon from '@mui/icons-material/Mic';
import PauseIcon from '@mui/icons-material/Pause';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import PlayCircleIcon from '@mui/icons-material/PlayCircle';
import SettingsIcon from '@mui/icons-material/Settings';
import StopIcon from '@mui/icons-material/Stop';
import UploadFileIcon from '@mui/icons-material/UploadFile';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import CircularProgress from '@mui/material/CircularProgress';
import IconButton from '@mui/material/IconButton';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import { useEffect, useRef, type ReactElement } from 'react';

import type { RecorderStatus } from '../hooks/useRecorder';
import { formatElapsed } from '../lib/transcript';
import { VuMeter } from './VuMeter';

const ACCEPTED_FILES = 'audio/*,video/mp4,.wav,.mp3,.m4a,.mp4,.webm,.ogg,.opus,.flac,.aac';

interface Props {
  transcript: string;
  onTranscriptChange: (text: string) => void;
  /** Keep the box scrolled to the end (progress output while transcribing). */
  followOutput: boolean;
  recorderStatus: RecorderStatus;
  elapsedMs: number;
  getLevel: () => number;
  recordUnavailableReason: string | null;
  busy: boolean;
  transcribing: boolean;
  canTranscribe: boolean;
  download: { url: string; name: string } | null;
  onStartRecording: () => void;
  onTogglePause: () => void;
  onStopRecording: () => void;
  onTranscribe: () => void;
  onImport: (file: File) => void;
  onOpenSettings: () => void;
}

/** Tooltip that also works on disabled buttons (they don't emit mouse events themselves). */
function Tip({ title, children }: { title: string; children: ReactElement }) {
  return (
    <Tooltip title={title}>
      <span>{children}</span>
    </Tooltip>
  );
}

export function TranscriptPanel(props: Props) {
  const {
    transcript, onTranscriptChange, followOutput, recorderStatus, elapsedMs, getLevel, recordUnavailableReason,
    busy, transcribing, canTranscribe, download,
  } = props;
  const fileInput = useRef<HTMLInputElement>(null);
  const textArea = useRef<HTMLTextAreaElement>(null);
  const recording = recorderStatus !== 'idle';

  useEffect(() => {
    if (followOutput && textArea.current) textArea.current.scrollTop = textArea.current.scrollHeight;
  }, [transcript, followOutput]);

  const insecure = !window.isSecureContext;

  return (
    <Stack sx={{ minHeight: 0, minWidth: 0 }}>
      {/* VU meter + timer */}
      <Stack direction="row" alignItems="center" spacing={1} sx={{ minHeight: 32 }}>
        <VuMeter active={recorderStatus === 'recording'} getLevel={getLevel} />
        <Typography sx={{ fontFamily: 'Consolas, "Roboto Mono", monospace', fontSize: 13 }}>
          {formatElapsed(elapsedMs)}
        </Typography>
      </Stack>

      {insecure && (
        <Alert
          severity="info"
          sx={{ mt: 1, py: 0 }}
          action={
            <Button color="inherit" size="small" href="/go-https">
              Přejít na HTTPS
            </Button>
          }
        >
          Nahrávání mikrofonu funguje jen přes HTTPS. Import souborů funguje i zde.
        </Alert>
      )}

      {/* Transcript */}
      <TextField
        multiline
        rows={10}
        value={transcript}
        onChange={(e) => onTranscriptChange(e.target.value)}
        inputRef={textArea}
        placeholder="Nahrajte nebo importujte schůzku, případně sem vložte přepis."
        sx={{
          flex: 1,
          minHeight: 160,
          my: 1,
          '& .MuiInputBase-root': { height: '100%', alignItems: 'stretch', fontSize: 13 },
          '& textarea': { height: '100% !important', overflow: 'auto !important', resize: 'none' },
        }}
        slotProps={{ htmlInput: { spellCheck: false, 'aria-label': 'Přepis' } }}
      />

      {/* Buttons */}
      <Box sx={{ display: 'grid', gridTemplateColumns: '1fr auto 1fr', alignItems: 'center' }}>
        <Box>
          <Tip title="Nastavení přepisu">
            <IconButton aria-label="Nastavení přepisu" onClick={props.onOpenSettings} disabled={transcribing}>
              <SettingsIcon />
            </IconButton>
          </Tip>
        </Box>

        <Stack direction="row" spacing={1}>
          <Tip title={recordUnavailableReason ?? 'Spustit nahrávání'}>
            <IconButton
              aria-label="Spustit nahrávání"
              onClick={props.onStartRecording}
              disabled={recording || busy || recordUnavailableReason !== null}
              color={recording ? 'error' : 'default'}
            >
              <MicIcon />
            </IconButton>
          </Tip>
          <Tip title={recorderStatus === 'paused' ? 'Pokračovat v nahrávání' : 'Pozastavit nahrávání'}>
            <IconButton
              aria-label={recorderStatus === 'paused' ? 'Pokračovat v nahrávání' : 'Pozastavit nahrávání'}
              onClick={props.onTogglePause}
              disabled={!recording}
            >
              {recorderStatus === 'paused' ? <PlayArrowIcon /> : <PauseIcon />}
            </IconButton>
          </Tip>
          <Tip title="Zastavit nahrávání">
            <IconButton aria-label="Zastavit nahrávání" onClick={props.onStopRecording} disabled={!recording}>
              <StopIcon />
            </IconButton>
          </Tip>
        </Stack>

        <Stack direction="row" justifyContent="flex-end" spacing={0.5}>
          {download && (
            <Tip title={`Stáhnout nahrávku (${download.name})`}>
              <IconButton aria-label="Stáhnout nahrávku" component="a" href={download.url} download={download.name}>
                <DownloadIcon />
              </IconButton>
            </Tip>
          )}
          <Tip title="Spustit přepis">
            <IconButton aria-label="Spustit přepis" onClick={props.onTranscribe} disabled={!canTranscribe}>
              {transcribing ? <CircularProgress size={24} /> : <PlayCircleIcon />}
            </IconButton>
          </Tip>
          <Tip title="Importovat soubor">
            <IconButton aria-label="Importovat soubor" onClick={() => fileInput.current?.click()} disabled={recording || busy}>
              <UploadFileIcon />
            </IconButton>
          </Tip>
          <input
            ref={fileInput}
            type="file"
            accept={ACCEPTED_FILES}
            hidden
            onChange={(e) => {
              const file = e.target.files?.[0];
              e.target.value = ''; // allow re-importing the same file
              if (file) props.onImport(file);
            }}
          />
        </Stack>
      </Box>
    </Stack>
  );
}
