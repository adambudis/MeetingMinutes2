# Model files

Mounted into the backend container as `/models`. Nothing here is downloaded at runtime, so the
server can run without internet access. Fill this folder during the online setup phase.

```
models/
├── canary-1b-v2.nemo              # 6.4 GB  - default ASR model (cs/en)
├── parakeet-tdt-0.6b-v3.nemo      # 2.5 GB  - optional ASR model
└── pyannote/hub/...               # 32 MB   - speaker diarization (Hugging Face cache layout)
    ├── models--pyannote--speaker-diarization-3.1/
    ├── models--pyannote--segmentation-3.0/
    ├── models--pyannote--wespeaker-voxceleb-resnet34-LM/
    └── models--pyannote--speaker-diarization-community-1/
```

- **NeMo models**: `deploy/download-models.sh` (or `.ps1`) downloads them from Hugging Face
  (`nvidia/canary-1b-v2`, `nvidia/parakeet-tdt-0.6b-v3`).
- **pyannote**: copied from the WPF project (`MeetingMinutes.Client/python/Models/pyannote`).
  When the cache is present the backend switches Hugging Face to offline mode automatically.

`GET /api/health` reports which of these files the backend can see.
