#!/usr/bin/env bash
# Download the NeMo speech-to-text models into ./models (online setup phase).
# Partial downloads are resumed when the script is run again.
#   deploy/download-models.sh            # canary + parakeet
#   deploy/download-models.sh canary     # only one of them
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p models

download() { # <hf-repo> <file>
    local target="models/$2"
    if [[ -f "$target" ]]; then
        echo "==> $2 already present"
        return
    fi
    echo "==> downloading $2"
    curl -fL --retry 5 -C - -o "$target.part" "https://huggingface.co/$1/resolve/main/$2"
    mv "$target.part" "$target"
}

which="${1:-all}"
if [[ $which == all || $which == canary ]]; then download nvidia/canary-1b-v2 canary-1b-v2.nemo; fi
if [[ $which == all || $which == parakeet ]]; then download nvidia/parakeet-tdt-0.6b-v3 parakeet-tdt-0.6b-v3.nemo; fi

if [[ ! -d models/pyannote/hub ]]; then
    echo "!! models/pyannote is missing - copy MeetingMinutes.Client/python/Models/pyannote from the WPF project"
fi
ls -lh models
