# syntax=docker/dockerfile:1.7
#
# MeetingMinutes backend (FastAPI + NeMo + pyannote). Builds for linux/amd64 and linux/arm64
# (e.g. DGX Spark). CUDA ships inside the PyTorch wheels; the host only needs the NVIDIA driver
# and the NVIDIA Container Toolkit.
#
#   TORCH_CUDA=cu130  -> CUDA 13.0 wheels, NVIDIA driver >= 580 (default; DGX Spark, RTX 50xx ...)
#   TORCH_CUDA=cu128  -> CUDA 12.8 wheels, NVIDIA driver >= 570
ARG BASE_IMAGE=python:3.12-slim

FROM ${BASE_IMAGE} AS builder
ARG TORCH_CUDA=cu130
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH=/opt/venv/bin:$PATH \
    LD_LIBRARY_PATH=/opt/venv/lib/python3.12/site-packages/nvidia/cu13/lib:/opt/venv/lib/python3.12/site-packages/nvidia/npp/lib
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*
RUN python -m venv /opt/venv

# 1) CUDA builds of torch/torchaudio/torchcodec from the PyTorch index (all three must match),
#    plus NVIDIA NPP, which the CUDA build of torchcodec links against. Separate layer, so
#    changing the requirements does not download the ~3.5 GB of CUDA wheels again.
RUN --mount=type=cache,target=/root/.cache/pip \
    case "$TORCH_CUDA" in \
      cu130) npp="nvidia-npp==13.0.3.3" ;; \
      cu128) npp="nvidia-npp-cu12==12.3.3.100" ;; \
      *) echo "unsupported TORCH_CUDA=$TORCH_CUDA (use cu130 or cu128)" >&2; exit 1 ;; \
    esac \
 && pip install --upgrade pip setuptools wheel \
 && pip install --index-url "https://download.pytorch.org/whl/${TORCH_CUDA}" --extra-index-url https://pypi.org/simple \
        "torch==2.10.0+${TORCH_CUDA}" "torchaudio==2.10.0+${TORCH_CUDA}" "torchcodec==0.10.0+${TORCH_CUDA}" "$npp"

# 2) Everything else from PyPI at the tested versions (constraints.txt = pip freeze of the
#    tested image). The installed +cuXXX torch satisfies the plain torch==2.10.0 pin and is kept.
WORKDIR /build
COPY requirements.txt requirements-ml.txt constraints.txt ./
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt -r requirements-ml.txt -c constraints.txt \
 && python -c "import torch; print('torch', torch.__version__, 'cuda', torch.version.cuda)"

FROM ${BASE_IMAGE} AS runtime
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg libsndfile1 \
 && rm -rf /var/lib/apt/lists/*
COPY --from=builder /opt/venv /opt/venv
# LD_LIBRARY_PATH: torchcodec has no RPATH to the pip-installed NPP libraries (path depends on
# the Python version of BASE_IMAGE: cu13 wheels use nvidia/cu13/lib, cu12 wheels nvidia/npp/lib).
ENV PATH=/opt/venv/bin:$PATH \
    LD_LIBRARY_PATH=/opt/venv/lib/python3.12/site-packages/nvidia/cu13/lib:/opt/venv/lib/python3.12/site-packages/nvidia/npp/lib \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MODELS_DIR=/models \
    HF_HOME=/models/pyannote \
    NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility
# Fail the build if the ML stack cannot be imported in the final image (torchcodec needs the
# FFmpeg libraries installed above and the NPP path from LD_LIBRARY_PATH).
RUN python -c "import torch, torchcodec, nemo.collections.asr, pyannote.audio; \
print('torch', torch.__version__, 'cuda', torch.version.cuda, '| torchcodec', torchcodec.__version__)" \
 && rm -rf /root/.cache
WORKDIR /app
COPY app ./app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health/live', timeout=4)" || exit 1
# One worker on purpose: models are loaded in-process and must exist only once in GPU memory.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--timeout-graceful-shutdown", "10"]
