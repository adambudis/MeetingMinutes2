#!/usr/bin/env bash
# Build all images for the server's CPU architecture and pack them into an offline bundle
# (run on a machine with internet; copy the resulting folder to the server).
#   deploy/build-bundle.sh linux/arm64            # DGX Spark / Grace
#   deploy/build-bundle.sh linux/amd64 [tag]      # x86 server
# Cross-building arm64 on an x86 machine works through QEMU emulation but is slow.
set -euo pipefail
cd "$(dirname "$0")/.."

PLATFORM="${1:-linux/amd64}"
TAG="${2:-$(date +%Y%m%d-%H%M)}"
OLLAMA_VERSION="${OLLAMA_VERSION:-0.40.16}"
TORCH_CUDA="${TORCH_CUDA:-cu130}"
OUT="bundle/meetingminutes-$TAG"

mkdir -p "$OUT/deploy" "$OUT/models"

echo "==> building images for $PLATFORM (tag $TAG, $TORCH_CUDA)"
DOCKER_DEFAULT_PLATFORM="$PLATFORM" TAG="$TAG" TORCH_CUDA="$TORCH_CUDA" docker compose build backend frontend
docker pull --platform "$PLATFORM" "ollama/ollama:$OLLAMA_VERSION"

images=("meetingminutes-backend:$TAG" "meetingminutes-frontend:$TAG" "ollama/ollama:$OLLAMA_VERSION")
echo "==> saving ${images[*]}"
docker save --platform "$PLATFORM" -o "$OUT/images.tar" "${images[@]}" \
    || docker save -o "$OUT/images.tar" "${images[@]}"   # older Docker without --platform

cp docker-compose.yml docker-compose.cpu.yml .env.example README.md "$OUT/"
cp deploy/install-bundle.sh deploy/pull-llm-models.sh "$OUT/deploy/"
cp models/README.md "$OUT/models/"
printf 'TAG=%s\nOLLAMA_VERSION=%s\nPLATFORM=%s\n' "$TAG" "$OLLAMA_VERSION" "$PLATFORM" > "$OUT/bundle.env"

echo "==> bundle ready: $OUT ($(du -sh "$OUT" | cut -f1))"
echo "    copy it to the server and run: sudo bash <bundle>/deploy/install-bundle.sh /opt/meetingminutes"
