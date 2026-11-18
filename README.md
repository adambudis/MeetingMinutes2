# MeetingMinutes

Records or imports meeting audio, transcribes it with speaker diarization (NVIDIA NeMo
Canary / Parakeet + pyannote) and writes structured meeting minutes with a local LLM (Ollama).
Everything runs on one NVIDIA machine; nothing leaves the network and no internet is needed
at runtime.

This is the client/server rewrite of the WPF desktop app in `MeetingMinutes-kral-update/`:

- `backend/` - FastAPI service that owns all model work (speech-to-text, diarization, LLM).
- `frontend/` - React UI with the same layout as the WPF window, served by nginx.
- `docker-compose.yml` - frontend + backend + Ollama, GPU-enabled, restarts on its own.

```
 Browser (any PC on the LAN)               NVIDIA AI PC - docker compose
 ┌───────────────────────┐   HTTPS    ┌──────────────────────────────────────────────────┐
 │ record / import audio │──────────▶ │ frontend   nginx: React UI, TLS, /api proxy      │
 │ transcript + chat     │            │    │                                             │
 └───────────────────────┘            │    ▼                                             │
                                      │ backend    FastAPI                               │
                                      │    ├─ ModelRunner: 1 GPU worker thread           │
                                      │    │    pyannote + NeMo Canary/Parakeet  ◀── ./models
                                      │    └─ map-reduce summarization ──▶ ollama ◀── ./data/ollama
                                      └──────────────────────────────────────────────────┘
```

## Repository layout

| Path | What |
|---|---|
| `backend/app/api/` | HTTP endpoints: `transcription.py`, `summarization.py`, `health.py` |
| `backend/app/services/` | Model services (see the mapping below) |
| `backend/tests/` | pytest suite (fake LLM/STT, runs without GPU or models) |
| `backend/constraints.txt` | Version pins from the original, tested Python environment |
| `frontend/src/` | React app: `App.tsx`, `components/`, `hooks/`, `api/`, `lib/` |
| `frontend/nginx/` | nginx config template + self-signed certificate generator |
| `deploy/` | Setup and offline-update scripts (`.sh` on the Linux server; `build-bundle.ps1` and `download-models.ps1` also for a Windows dev PC) |
| `models/` | Model weights, mounted into the backend (not in git; see `models/README.md`) |
| `data/` | Runtime data: Ollama models, TLS certificate (created on first start) |

### Where the C# code went

| WPF / C# | New |
|---|---|
| `ITranscriptionService`, `LocalPythonTranscriptionService` + `python/app.py` (subprocess per run) | `services/transcription.py` - in-process, models cached in GPU memory |
| `python/services/diarization_service.py` | `services/diarization.py` |
| `ILlmService`, `OllamaLlmService` | `services/ollama_llm.py` |
| `ISummarizationService`, `SummarizationService` (map-reduce, action items) | `services/summarization.py` (same prompts and algorithm) |
| `ServiceFactory` | `services/factory.py` (FastAPI dependency providers) |
| NAudio recording + MediaFoundation conversion | browser `MediaRecorder` (`hooks/useRecorder.ts`) + ffmpeg on the server (`services/audio.py`) |
| `MainWindow.xaml(.cs)` | `App.tsx`, `TranscriptPanel.tsx`, `ChatPanel.tsx` |
| `SettingsDialogView`, `TranscriptionSettingsDialogView`, `SpeakerRenameDialogView` | `components/dialogs/*` |
| `UserSettings` (`%APPDATA%`) | `hooks/useSettings.ts` (browser localStorage) |

## API

All long-running endpoints stream [Server-Sent Events](https://developer.mozilla.org/docs/Web/API/Server-sent_events)
over the POST response, with a `: keep-alive` comment every 15 s. Interactive docs: `/api/docs`.

| Endpoint | Request | Events |
|---|---|---|
| `POST /api/transcribe` | multipart: `file`, `model` (`canary`\|`parakeet`), `language` (`cs`\|`en`) | `progress {message}`... then `result {segments:[{start,end,speaker,text}]}` or `error {message}` |
| `POST /api/summarize` | `{transcript, model?, segments?}` | `warning {message}`?, `chunk {current,total}`, `token {text}`..., `done {markdown, map_success_ratio}` or `error` |
| `POST /api/chat` | `{messages:[{role,content}], model?}` | `token {text}`..., `done {text}` or `error` |
| `GET /api/transcribe/models` | | which ASR models exist on disk |
| `GET /api/llm/models` | | default + installed Ollama models |
| `GET /api/health` | | GPU, model files, Ollama status (`/api/health/live` = liveness) |

Model jobs run one at a time on a single worker thread (one copy of each model in GPU memory);
concurrent requests wait in a queue and are told so. Closing the browser tab cancels LLM
generation; a queued transcription is dropped, a running one finishes and is discarded.

## Development

Backend (Python 3.11+). The API layer and tests need no GPU or ML libraries:

```bash
cd backend
python -m venv .venv && .venv/Scripts/activate        # Linux: source .venv/bin/activate
pip install -r requirements-dev.txt -c constraints.txt
pytest
OLLAMA_BASE_URL=http://localhost:11434 uvicorn app.main:app --port 8000
```

Real transcription additionally needs `pip install -r requirements-ml.txt -c constraints.txt`
(after installing a CUDA build of torch/torchaudio/torchcodec, see `backend/Dockerfile`) and the
model files in `models/`.

`backend/constraints.txt` is the `pip freeze` of the tested backend image, so every build
installs exactly the tested versions. After changing `requirements*.txt`, build and test the
image, then refresh the lock (the CUDA-specific packages stay unpinned on purpose):

```bash
docker run --rm meetingminutes-backend:latest pip freeze \
  | grep -viE '^(torch|torchaudio|torchcodec|triton|cuda-bindings|cuda-pathfinder|nvidia-[a-z0-9-]+)==' \
  > pins.txt   # then replace the pins in backend/constraints.txt (keep the header and torch lines)
```

Frontend (Node 22+):

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173, proxies /api to http://127.0.0.1:8000
npm run lint && npm test && npm run build
```

## Deployment on the NVIDIA AI PC

The plan: install everything while the machine still has internet, then move it to the
server room where it runs offline. Later updates arrive as a bundle of Docker images.

### 1. Online setup (hands-on access, internet available)

1. **Host prerequisites (Linux).** DGX OS on a DGX Spark ships with all of them; on a plain
   Ubuntu install them:
   - NVIDIA driver >= 580 (for the default CUDA 13 build; >= 570 with `TORCH_CUDA=cu128`),
   - Docker Engine with the Compose v2 plugin
     ([docs.docker.com/engine/install](https://docs.docker.com/engine/install/)),
   - [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html),
     registered with Docker: `sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker`.

   Then make sure Docker starts at boot and check GPU access from a container:
   ```bash
   sudo systemctl enable --now docker containerd
   sudo usermod -aG docker $USER        # optional: docker without sudo (log in again)
   docker run --rm --gpus all ubuntu nvidia-smi
   ```
   If a firewall is active, open the web ports: `sudo ufw allow 80,443/tcp`. For remote
   administration from the dev PC, enable SSH: `sudo apt install openssh-server`.
2. Copy this repository to the machine (e.g. `/opt/meetingminutes`) and `cp .env.example .env`.
3. Models into `./models` - `deploy/download-models.sh` fetches Canary (6.4 GB) and Parakeet
   (2.5 GB); copy `models/pyannote` along from your checkout (it is not in git).
4. Build and start: `docker compose up -d --build`. Building on the target machine itself
   produces the right CPU architecture (x86 or ARM64, e.g. DGX Spark) automatically.
5. LLMs into `./data/ollama`: `deploy/pull-llm-models.sh` (gemma3:12b, gemma3:4b, qwen2.5:14b).
6. Smoke test: open `https://<machine>/`, check `https://<machine>/api/health` (`"status": "ok"`,
   `"device": "cuda"`), transcribe and summarize a short recording.
7. Reboot once and confirm everything comes back by itself (`docker compose ps`), since that's
   what will happen in the server room.
8. Note the CPU architecture (`uname -m`: `aarch64` = build bundles with `linux/arm64`,
   `x86_64` = `linux/amd64`) and the installed driver version (`nvidia-smi`) for later updates.

### 2. Running in the server room (offline)

- All containers have `restart: unless-stopped` and Docker is enabled at boot (step 1), so after
  a power cut or reboot the system comes back on its own.
- Nothing is downloaded at runtime; Hugging Face is switched to offline mode automatically
  because the pyannote cache is present.
- **Address / certificate**: once you know how users will reach the server, put the host names
  and/or IPs into `SERVER_HOSTS` in `.env` (e.g. `SERVER_HOSTS=meetings.company.local,10.0.5.20`)
  and run `docker compose up -d`. A new self-signed certificate for these names is generated on
  start. To use a company certificate, place `server.crt` + `server.key` into `data/certs/` and
  delete `data/certs/.generated-for`.
- Microphone recording requires HTTPS (browsers block it on plain `http://` except for
  localhost). With the self-signed certificate users confirm a browser warning once, or IT
  distributes `data/certs/server.crt` as a trusted certificate. Importing files works over HTTP too.
- Remote administration from the dev PC over SSH: `docker compose ps`, `docker compose logs -f backend`,
  `curl -k https://localhost/api/health`.

### 3. Updates without internet

On a machine with internet and Docker (your dev PC):

```powershell
.\deploy\build-bundle.ps1 -Platform linux/arm64   # DGX Spark / Grace; linux/amd64 for x86
```
```bash
deploy/build-bundle.sh linux/arm64                # same on Linux/macOS
```

This builds the images for the server's architecture (cross-building ARM64 on an x86 PC works
through emulation but takes a while) and writes `bundle/meetingminutes-<tag>/` with
`images.tar` (several GB), the compose files and the install scripts. Copy the folder to the
server (scp/USB) and run:

```bash
scp -r bundle/meetingminutes-<tag> admin@<server>:/tmp/            # from the dev PC
sudo bash /tmp/meetingminutes-<tag>/deploy/install-bundle.sh /opt/meetingminutes
```

`.env`, `models/` and `data/` are kept. The previous version stays in Docker; to roll back set
`TAG=<previous tag>` in `.env` and run `docker compose up -d`.

New LLMs for an offline server: pull them on any machine with the same Ollama version and copy
`~/.ollama/models` (or that machine's `data/ollama/models`) into the server's `data/ollama/models`.

## Configuration (`.env`)

| Variable | Default | Meaning |
|---|---|---|
| `SERVER_HOSTS` | `localhost` | Host names/IPs for the HTTPS certificate (comma-separated) |
| `HTTP_PORT` / `HTTPS_PORT` | `80` / `443` | Published ports |
| `TAG` | `latest` | Version of the meetingminutes images (set by `install-bundle`) |
| `OLLAMA_VERSION` | `0.40.16` | `ollama/ollama` image tag |
| `TORCH_CUDA` | `cu130` | PyTorch CUDA build: `cu130` (driver >= 580) or `cu128` (driver >= 570) |
| `OLLAMA_BASE_URL` | `http://ollama:11434` | Use `http://host.docker.internal:11434` for an Ollama installed on the host |
| `DEFAULT_LLM_MODEL` | `gemma3:12b` | Used when the client does not choose a model |
| `LLM_NUM_CTX` | `65536` | Context window requested from Ollama (as in the WPF app) |
| `OLLAMA_KEEP_ALIVE` / `OLLAMA_NUM_PARALLEL` | `30m` / `1` | How long a model stays loaded / parallel requests |
| `WARMUP_MODELS` | `canary` | ASR models loaded at start-up (empty = on first use) |
| `MAX_UPLOAD_MB` | `500` | Upload limit (nginx and backend) |
| `HF_TOKEN` | | Only for downloading pyannote models during setup |

No NVIDIA GPU (e.g. a development laptop):
`docker compose -f docker-compose.yml -f docker-compose.cpu.yml up -d --build`.

## Troubleshooting

| Symptom | Check |
|---|---|
| `/api/health` says `"device": "cpu"` | `docker run --rm --gpus all ubuntu nvidia-smi`; driver version vs. `TORCH_CUDA` |
| `"pyannote_cached": false` | `models/pyannote/hub/models--pyannote--speaker-diarization-3.1/` must exist |
| `"models": {"canary": false}` | `models/canary-1b-v2.nemo` missing |
| Summary fails with "Model ... není v Ollama stažen" | `docker compose exec ollama ollama list`; pull or copy the model |
| Microphone button disabled | page opened over `http://` - use `https://` |
| Large uploads fail | `MAX_UPLOAD_MB` in `.env`, then `docker compose up -d` |
| Anything else | `docker compose logs -f backend` |

## Differences from the WPF version

Behaviour and prompts were kept, with these deliberate changes:

- **Action items work now.** The original asked the LLM for a bare JSON array; with Ollama's
  JSON mode the model answers with a single object, which the C# deserializer rejected, so the
  "Akční položky" table was always empty. The array is now wrapped in `{"items": [...]}` and
  enforced with a JSON schema; verified against gemma3 with real meeting text.
- **The final summary is displayed.** The WPF client kept the streamed text (`"[3/3] " + reduce
  output`) instead of the final Markdown, so the action-items table never appeared.
- LLM output is cleaned up before rendering: an answer wrapped entirely in a ```` ```markdown ````
  fence is unwrapped, and sections a model indented by 4+ spaces under a heading are
  un-indented. Markdown would otherwise show both as grey code blocks (seen with gemma3:4b).
- Follow-up questions no longer send an empty assistant message as the last history entry.
- Removing a stray task table from the LLM output no longer also deletes the next table.
- Models stay loaded between transcriptions (the subprocess reloaded them every time).
- A failed transcription keeps the file queued for a retry; timestamps past one hour show
  `h:mm:ss` instead of wrapping.
