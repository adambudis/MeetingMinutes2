import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import Snackbar from '@mui/material/Snackbar';
import { useEffect, useRef, useState } from 'react';

import { chat, errorText, isAbortError, summarize, transcribe, type ChatRequestMessage } from './api/client';
import { ChatPanel } from './components/ChatPanel';
import { SettingsDialog } from './components/dialogs/SettingsDialog';
import { SpeakerRenameDialog } from './components/dialogs/SpeakerRenameDialog';
import { TranscriptionSettingsDialog } from './components/dialogs/TranscriptionSettingsDialog';
import { TranscriptPanel } from './components/TranscriptPanel';
import { useNotifications } from './hooks/useNotifications';
import { recordingUnavailableReason, useRecorder } from './hooks/useRecorder';
import { useSettings } from './hooks/useSettings';
import {
  DEFAULT_SUMMARY_PROMPT,
  formatForDisplay,
  formatPendingInfo,
  recordingFileName,
  renameSpeakers,
  uniqueSpeakers,
} from './lib/transcript';
import type { ChatMessage, PendingAudio, TranscriptSegment, UserSettings } from './types';

let nextMessageId = 1;
const newMessage = (role: ChatMessage['role'], content: string, streaming: boolean): ChatMessage => ({
  id: `m${nextMessageId++}`, // crypto.randomUUID() is unavailable on plain-HTTP origins
  role,
  content,
  streaming,
});

export default function App() {
  const [settings, saveSettings] = useSettings();
  const recorder = useRecorder();
  const { current: notice, notify, dismiss } = useNotifications();

  const [transcript, setTranscript] = useState('');
  /** The box shows status text (recording / pending / progress), not a transcript. */
  const [transcriptIsInfo, setTranscriptIsInfo] = useState(false);
  const [segments, setSegments] = useState<TranscriptSegment[] | null>(null);
  const [pending, setPending] = useState<PendingAudio | null>(null);
  const [transcribing, setTranscribing] = useState(false);
  const [renameLabels, setRenameLabels] = useState<string[] | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [chatBusy, setChatBusy] = useState(false);
  const [dialog, setDialog] = useState<'settings' | 'transcription' | null>(null);
  const [unavailableReason] = useState(recordingUnavailableReason);

  const chatAbort = useRef<AbortController | null>(null);
  const transcribeAbort = useRef<AbortController | null>(null);

  // Release the recording's object URL when it is replaced or dropped.
  useEffect(() => {
    const url = pending?.downloadUrl;
    return () => {
      if (url) URL.revokeObjectURL(url);
    };
  }, [pending]);

  useEffect(
    () => () => {
      chatAbort.current?.abort();
      transcribeAbort.current?.abort();
    },
    [],
  );

  const showInfo = (text: string) => {
    setTranscript(text);
    setTranscriptIsInfo(true);
  };

  const clearChat = () => {
    chatAbort.current?.abort();
    setMessages([]);
  };

  const preparePending = (audio: PendingAudio) => {
    setSegments(null);
    setRenameLabels(null);
    setPending(audio);
    showInfo(formatPendingInfo(audio.header, settings));
  };

  // --- Recording -------------------------------------------------------------------------

  const handleStartRecording = async () => {
    setPending(null);
    setSegments(null);
    showInfo('Nahrávám...');
    try {
      await recorder.start();
    } catch (e) {
      setTranscript('');
      setTranscriptIsInfo(false);
      notify(`Chyba při spuštění nahrávání: ${errorText(e)}`);
    }
  };

  const handleStopRecording = async () => {
    const recording = await recorder.stop();
    if (!recording || recording.blob.size === 0) {
      setTranscript('');
      setTranscriptIsInfo(false);
      notify('Nahrávka je prázdná.');
      return;
    }
    const name = recordingFileName(recording.mimeType);
    preparePending({
      blob: recording.blob,
      name,
      header: `Nahrávání dokončeno: ${name}`,
      downloadUrl: URL.createObjectURL(recording.blob),
    });
  };

  const handleImport = (file: File) => preparePending({ blob: file, name: file.name, header: `Importováno: ${file.name}` });

  // --- Transcription ---------------------------------------------------------------------

  const handleTranscribe = async () => {
    if (!pending || transcribing) return;
    const audio = pending;
    const lines = [`Odesílám ${audio.name} na server...`];
    const render = () => showInfo(lines.join('\n'));
    render();
    setTranscribing(true);
    const controller = new AbortController();
    transcribeAbort.current = controller;

    try {
      const result = await transcribe({
        file: audio.blob,
        fileName: audio.name,
        model: settings.transcriptionModel,
        language: settings.transcriptionLanguage,
        signal: controller.signal,
        onUploadProgress: (fraction) => {
          lines[0] = `Odesílám ${audio.name} na server... ${Math.round(fraction * 100)} %`;
          render();
        },
        onProgress: (message) => {
          lines.push(message);
          render();
        },
      });
      setPending(null);
      setSegments(result);
      setTranscript(formatForDisplay(result));
      setTranscriptIsInfo(false);
      clearChat();
      if (result.length === 0) notify('Přepis neobsahuje žádný text.');
      else setRenameLabels(uniqueSpeakers(result));
    } catch (e) {
      if (isAbortError(e)) return;
      lines.push('', `[Chyba: ${errorText(e)}]`);
      render(); // the file stays pending so the user can retry
    } finally {
      setTranscribing(false);
      transcribeAbort.current = null;
    }
  };

  const handleRename = (names: Record<string, string>) => {
    setRenameLabels(null);
    if (!segments || Object.keys(names).length === 0) return;
    if (transcript !== formatForDisplay(segments)) {
      notify('Manuální úpravy v boxu — přejmenování zrušeno');
      return;
    }
    const renamed = renameSpeakers(segments, names);
    setSegments(renamed);
    setTranscript(formatForDisplay(renamed));
  };

  // --- Summary & chat --------------------------------------------------------------------

  const canSend = !transcriptIsInfo && !transcribing && recorder.status === 'idle' && transcript.trim().length > 0;

  const handleSend = async (prompt: string) => {
    if (chatBusy) return;
    if (!canSend) {
      notify('Není k dispozici žádný přepis.');
      return;
    }
    const userText = prompt.trim() || DEFAULT_SUMMARY_PROMPT;
    const isFirst = messages.length === 0;
    const history: ChatRequestMessage[] = messages
      .filter((m) => !m.failed)
      .map((m) => ({ role: m.role, content: m.content }));

    // Manual edits invalidate the structured segments; the edited text is used instead.
    const validSegments = segments && transcript === formatForDisplay(segments) ? segments : null;
    if (segments && !validSegments) setSegments(null);

    const reply = newMessage('assistant', '', true);
    setMessages((prev) => [...prev, newMessage('user', userText, false), reply]);
    const update = (patch: (m: ChatMessage) => Partial<ChatMessage>) =>
      setMessages((prev) => prev.map((m) => (m.id === reply.id ? { ...m, ...patch(m) } : m)));

    const controller = new AbortController();
    chatAbort.current = controller;
    setChatBusy(true);
    try {
      if (isFirst) {
        const events = summarize(
          { transcript: validSegments ? '' : transcript, model: settings.ollamaModel, segments: validSegments },
          controller.signal,
        );
        for await (const ev of events) {
          switch (ev.event) {
            case 'warning':
              notify(ev.data.message);
              break;
            case 'chunk':
              update(() => ({ content: `[${ev.data.current}/${ev.data.total}] ` }));
              break;
            case 'token':
              update((m) => ({ content: m.content + ev.data.text }));
              break;
            case 'done': {
              update(() => ({ content: ev.data.markdown }));
              const ratio = ev.data.map_success_ratio;
              if (ratio < 0.5) notify(`Některé části přepisu se nepodařilo zpracovat (úspěšnost ${Math.round(ratio * 100)} %)`);
              break;
            }
            case 'error':
              update(() => ({ content: `[Chyba: ${ev.data.message}]`, failed: true }));
              break;
          }
        }
      } else {
        const events = chat(
          { messages: [...history, { role: 'user', content: userText }], model: settings.ollamaModel },
          controller.signal,
        );
        for await (const ev of events) {
          if (ev.event === 'token') update((m) => ({ content: m.content + ev.data.text }));
          else if (ev.event === 'error') update(() => ({ content: `[Chyba: ${ev.data.message}]`, failed: true }));
        }
      }
    } catch (e) {
      if (isAbortError(e)) update((m) => ({ content: `${m.content}\n\n[Zrušeno uživatelem]`, failed: true }));
      else update(() => ({ content: `[Chyba: ${errorText(e)}]`, failed: true }));
    } finally {
      update(() => ({ streaming: false }));
      setChatBusy(false);
      if (chatAbort.current === controller) chatAbort.current = null;
    }
  };

  // --- Settings ----------------------------------------------------------------------------

  const handleSaveSettings = (next: UserSettings) => {
    saveSettings(next);
    setDialog(null);
    if (pending && transcriptIsInfo && !transcribing) showInfo(formatPendingInfo(pending.header, next));
  };

  const busy = transcribing || renameLabels !== null;

  return (
    <Box sx={{ height: '100vh', '@supports (height: 100dvh)': { height: '100dvh' }, p: 1 }}>
      <Card
        elevation={4}
        sx={{
          height: '100%',
          p: 1,
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', md: '1fr auto 1fr' },
          gridTemplateRows: { xs: 'minmax(360px, 1fr) minmax(360px, 1fr)', md: 'minmax(0, 1fr)' },
          rowGap: 2,
          overflow: { xs: 'auto', md: 'hidden' },
        }}
      >
        <TranscriptPanel
          transcript={transcript}
          onTranscriptChange={(text) => {
            setTranscript(text);
            setTranscriptIsInfo(false);
          }}
          followOutput={transcribing}
          recorderStatus={recorder.status}
          elapsedMs={recorder.elapsedMs}
          getLevel={recorder.getLevel}
          recordUnavailableReason={unavailableReason}
          busy={busy}
          transcribing={transcribing}
          canTranscribe={pending !== null && !busy && recorder.status === 'idle'}
          download={pending?.downloadUrl ? { url: pending.downloadUrl, name: pending.name } : null}
          onStartRecording={handleStartRecording}
          onTogglePause={recorder.togglePause}
          onStopRecording={handleStopRecording}
          onTranscribe={handleTranscribe}
          onImport={handleImport}
          onOpenSettings={() => setDialog('transcription')}
        />

        <Box sx={{ display: { xs: 'none', md: 'block' }, width: '1px', mx: 1, bgcolor: 'divider' }} />

        <ChatPanel
          messages={messages}
          busy={chatBusy}
          canSend={canSend}
          onSend={handleSend}
          onCancel={() => chatAbort.current?.abort()}
          onClear={clearChat}
          onOpenSettings={() => setDialog('settings')}
        />
      </Card>

      {dialog === 'settings' && (
        <SettingsDialog settings={settings} onClose={() => setDialog(null)} onSave={handleSaveSettings} />
      )}
      {dialog === 'transcription' && (
        <TranscriptionSettingsDialog settings={settings} onClose={() => setDialog(null)} onSave={handleSaveSettings} />
      )}
      {renameLabels && (
        <SpeakerRenameDialog labels={renameLabels} onConfirm={handleRename} onSkip={() => setRenameLabels(null)} />
      )}

      <Snackbar
        key={notice?.key}
        open={notice !== null}
        message={notice?.message}
        autoHideDuration={6000}
        onClose={(_, reason) => reason !== 'clickaway' && dismiss()}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      />
    </Box>
  );
}
