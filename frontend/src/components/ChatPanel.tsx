import DeleteSweepIcon from '@mui/icons-material/DeleteSweep';
import SendIcon from '@mui/icons-material/Send';
import SettingsIcon from '@mui/icons-material/Settings';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import IconButton from '@mui/material/IconButton';
import InputBase from '@mui/material/InputBase';
import Stack from '@mui/material/Stack';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import { memo, useEffect, useRef, useState } from 'react';

import { toolbarBackground } from '../theme';
import type { ChatMessage } from '../types';
import { MarkdownView } from './MarkdownView';

const Bubble = memo(function Bubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === 'user';
  return (
    <Box
      sx={{
        alignSelf: isUser ? 'flex-end' : 'flex-start',
        maxWidth: isUser ? 380 : '94%',
        px: 1.25,
        py: 1,
        mx: 0.5,
        my: 0.375,
        // WPF CornerRadius order is the same as CSS: top-left, top-right, bottom-right, bottom-left
        borderRadius: isUser ? '14px 14px 2px 14px' : '14px 14px 14px 2px',
        bgcolor: isUser ? 'primary.main' : toolbarBackground,
        color: isUser ? 'primary.contrastText' : 'text.primary',
        overflowWrap: 'anywhere',
      }}
    >
      {isUser || message.streaming ? (
        <Typography component="div" sx={{ fontSize: 13, whiteSpace: 'pre-wrap' }}>
          {message.content || (message.streaming ? '…' : '')}
        </Typography>
      ) : (
        <MarkdownView text={message.content} />
      )}
    </Box>
  );
});

interface Props {
  messages: ChatMessage[];
  busy: boolean;
  canSend: boolean;
  onSend: (prompt: string) => void;
  onCancel: () => void;
  onClear: () => void;
  onOpenSettings: () => void;
}

export function ChatPanel({ messages, busy, canSend, onSend, onCancel, onClear, onOpenSettings }: Props) {
  const [prompt, setPrompt] = useState('');
  const list = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);

  // Follow streaming output unless the user scrolled up to read.
  useEffect(() => {
    const el = list.current;
    if (el && stickToBottom.current) el.scrollTop = el.scrollHeight;
  }, [messages]);

  const send = () => {
    if (busy || !canSend) return;
    onSend(prompt);
    setPrompt('');
    stickToBottom.current = true;
  };

  return (
    <Stack sx={{ minHeight: 0, minWidth: 0 }}>
      <Box
        ref={list}
        onScroll={(e) => {
          const el = e.currentTarget;
          stickToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
        }}
        sx={{ flex: 1, minHeight: 0, overflowY: 'auto', display: 'flex', flexDirection: 'column', pr: 0.5 }}
      >
        {messages.length === 0 && (
          <Typography color="text.secondary" sx={{ m: 'auto', textAlign: 'center', px: 2, fontSize: 13 }}>
            Po přepisu odešlete zprávu (nebo nechte pole prázdné) a vytvoří se shrnutí schůzky.
          </Typography>
        )}
        {messages.map((m) => (
          <Bubble key={m.id} message={m} />
        ))}
      </Box>

      {/* Input bar */}
      <Stack
        direction="row"
        alignItems="center"
        sx={{ mt: 1, px: 1, py: 0.5, borderRadius: 6, bgcolor: toolbarBackground }}
      >
        <InputBase
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              send();
            }
          }}
          placeholder="Napište zprávu..."
          sx={{ flex: 1, px: 1, fontSize: 13 }}
          slotProps={{ input: { 'aria-label': 'Zpráva' } }}
        />
        {busy ? (
          <Tooltip title="Klikněte pro zrušení" describeChild>
            <Button size="small" onClick={onCancel}>
              Zrušit
            </Button>
          </Tooltip>
        ) : (
          <Tooltip title="Odeslat">
            <span>
              <IconButton aria-label="Odeslat" onClick={send} disabled={!canSend}>
                <SendIcon />
              </IconButton>
            </span>
          </Tooltip>
        )}
        <Tooltip title="Vymazat konverzaci">
          <span>
            <IconButton aria-label="Vymazat konverzaci" onClick={onClear} disabled={busy || messages.length === 0}>
              <DeleteSweepIcon />
            </IconButton>
          </span>
        </Tooltip>
        <Tooltip title="Nastavení">
          <IconButton aria-label="Nastavení" onClick={onOpenSettings}>
            <SettingsIcon />
          </IconButton>
        </Tooltip>
      </Stack>
    </Stack>
  );
}
