#!/usr/bin/env bash
# Start the ROBUST TAMP planner server: vLLM (OpenAI-compatible API) serving the pinned
# Qwen3-VL-8B-Thinking snapshot on 127.0.0.1:8000, inside tmux session "vllm", window "serve".
# Idempotent: if the server already answers, or a "serve" window exists, nothing is started.
# Reach it from a workstation with:
#   ssh -i ~/keyfile -N -L 8000:127.0.0.1:8000 long-horizon@gvlab2.iiit.ac.in
set -euo pipefail

ROOT="$HOME/robust_tamp_infer"
VENV="$ROOT/.venv"
LOG_DIR="$ROOT/logs"
SESSION="vllm"
WINDOW="serve"
HOST="127.0.0.1"
PORT="${VLLM_PORT:-8000}"
MODEL_REPO="Qwen/Qwen3-VL-8B-Thinking"
MODEL_REVISION="92f3c4b4feadd3a016ef468d103bb5f58b2a2c6b"   # pinned snapshot (Hub main on 2026-09-26)
SERVED_NAME="qwen3-vl-8b-thinking"
MAX_MODEL_LEN="${VLLM_MAX_MODEL_LEN:-32768}"
GPU_UTIL="${VLLM_GPU_UTIL:-0.90}"
# One GPU on this server (RTX 5090); use every visible GPU if more are added and free.
TP_SIZE="${VLLM_TP_SIZE:-$(nvidia-smi --query-gpu=index --format=csv,noheader | wc -l)}"

export HF_HOME="${HF_HOME:-/home/projects/long-horizon/.cache/huggingface}"
export HF_HUB_OFFLINE=1          # serve the local pinned snapshot; no network at start-up
# flashinfer JIT-compiles its sampling kernels at warm-up: it needs ninja (in the venv) and nvcc.
export CUDA_HOME="${CUDA_HOME:-/usr/local/cuda}"
export PATH="$VENV/bin:$CUDA_HOME/bin:$PATH"
ENV_EXPORTS="export HF_HOME=$HF_HOME HF_HUB_OFFLINE=1 CUDA_HOME=$CUDA_HOME PATH=$PATH"

mkdir -p "$LOG_DIR"

if curl -sf --max-time 5 "http://$HOST:$PORT/v1/models" 2>/dev/null | grep -q "\"$SERVED_NAME\""; then
    echo "vLLM already serving $SERVED_NAME on $HOST:$PORT"; exit 0
fi
if tmux has-session -t "$SESSION" 2>/dev/null && tmux list-windows -t "$SESSION" -F "#W" | grep -qx "$WINDOW"; then
    echo "tmux window $SESSION:$WINDOW exists (server still loading?); see $LOG_DIR/vllm_latest.log"; exit 0
fi
if ss -ltn "sport = :$PORT" | grep -q LISTEN; then
    echo "port $PORT is in use by another process; not starting" >&2; exit 1
fi

LOG="$LOG_DIR/vllm_$(date +%Y%m%d_%H%M%S).log"
ln -sfn "$LOG" "$LOG_DIR/vllm_latest.log"
# Serve the pinned snapshot directory itself: vLLM then reports it as the model "root" in
# GET /v1/models, which is how the planner client verifies the revision on every call.
SNAPSHOT="$HF_HOME/hub/models--${MODEL_REPO//\//--}/snapshots/$MODEL_REVISION"
[ -f "$SNAPSHOT/config.json" ] || { echo "pinned snapshot missing: $SNAPSHOT" >&2; exit 1; }
CMD=("$VENV/bin/vllm" serve "$SNAPSHOT"
     --served-model-name "$SERVED_NAME"
     --host "$HOST" --port "$PORT"
     --tensor-parallel-size "$TP_SIZE"
     --max-model-len "$MAX_MODEL_LEN"
     --gpu-memory-utilization "$GPU_UTIL"
     --reasoning-parser qwen3
     --limit-mm-per-prompt "{\"image\": 2, \"video\": 0}"
     --generation-config auto)
printf "%q " "${CMD[@]}" > "$LOG_DIR/serve_command.txt"; echo >> "$LOG_DIR/serve_command.txt"
RUN="$(printf "%q " "${CMD[@]}") 2>&1 | tee -a $(printf "%q" "$LOG")"
if tmux has-session -t "$SESSION" 2>/dev/null; then
    tmux new-window -d -t "$SESSION" -n "$WINDOW" "bash -lc $(printf "%q" "$ENV_EXPORTS; $RUN")"
else
    tmux new-session -d -s "$SESSION" -n "$WINDOW" "bash -lc $(printf "%q" "$ENV_EXPORTS; $RUN")"
fi
echo "started $SESSION:$WINDOW; log $LOG"
echo "waiting for http://$HOST:$PORT/v1/models ..."
for _ in $(seq 1 180); do
    if curl -sf --max-time 5 "http://$HOST:$PORT/v1/models" >/dev/null 2>&1; then echo "ready"; exit 0; fi
    tmux list-windows -t "$SESSION" -F "#W" 2>/dev/null | grep -qx "$WINDOW" || { echo "server exited; see $LOG" >&2; exit 1; }
    sleep 5
done
echo "not ready after 15 min; see $LOG" >&2; exit 1
