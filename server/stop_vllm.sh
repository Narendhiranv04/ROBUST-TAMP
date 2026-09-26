#!/usr/bin/env bash
# Stop the vLLM server started by start_vllm.sh (tmux session "vllm", window "serve" only).
set -uo pipefail
SESSION="vllm"; WINDOW="serve"; PORT="${VLLM_PORT:-8000}"
if ! tmux list-windows -t "$SESSION" -F "#W" 2>/dev/null | grep -qx "$WINDOW"; then
    echo "no $SESSION:$WINDOW window; nothing to stop"; exit 0
fi
tmux send-keys -t "$SESSION:$WINDOW" C-c
for _ in $(seq 1 30); do
    tmux list-windows -t "$SESSION" -F "#W" 2>/dev/null | grep -qx "$WINDOW" || break
    ss -ltn "sport = :$PORT" | grep -q LISTEN || { tmux kill-window -t "$SESSION:$WINDOW" 2>/dev/null; break; }
    sleep 2
done
tmux kill-window -t "$SESSION:$WINDOW" 2>/dev/null || true
echo "stopped"; nvidia-smi --query-gpu=index,memory.used --format=csv,noheader
