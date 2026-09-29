#!/usr/bin/env bash
# ICL (examples_v2) with the selected planner on the grill variants, then the Ministral rows of Table 2 (b).
set -uo pipefail
INFER=$HOME/robust_tamp_infer
. "$INFER/sim_env.sh" >/dev/null
REPO=$HOME/robust_tamp_run
RUN=$INFER/real_trials/v2/icl/qwen3-vl-8b-thinking
mkdir -p "$RUN" "$INFER/archive/v2/icl"
export LLM_REQUEST_TIMEOUT_S=1800
GRILL="FINAL.G0 FINAL.G1 FINAL.G2 FINAL.G3 FINAL.G1-n1"
FULL="--flag memory.enabled=true --flag replan.trigger_mode=if_rule --flag replan.output_mode=corrective --flag replan.insertion_mode=planner --flag parallel.enabled=true"
log() { echo "[icl $(date -Is)] $*"; }
git -C "$REPO" log --oneline -1; git -C "$REPO" status --short -uno
if [ ! -f "$RUN/COMPLETE" ]; then
  "$REPO/server/stop_vllm.sh" >/dev/null 2>&1; sleep 5
  VLLM_MODEL=qwen3-vl-8b-thinking "$REPO/server/start_vllm.sh" || { log "vLLM did not start"; exit 1; }
  cp "$INFER/logs/serve_command.txt" "$RUN/serve_command.txt"
  log "grill x 0-9 with examples_v2"
  nice -n 5 python -m llm_pipeline.run_trial_matrix --planner model --jobs 6 --timeout 14400 --variants $GRILL --seeds 0-9 \
    --out "$RUN" --title "qwen3-vl-8b-thinking, ICL examples_v2, grill" -- --model qwen3-vl-8b-thinking --model-type vlm --vision \
    --remote --remote-api openai --remote-url http://127.0.0.1:8000 --planner-max-new-tokens 24576 --icl-mode examples_v2 $FULL \
    > "$RUN/matrix.log" 2>&1
  curl -s --max-time 30 http://127.0.0.1:8000/metrics > "$RUN/vllm_metrics.prom"
  python -m evaluation.model_run_report "$RUN" --variants $GRILL --seeds 0-9 > "$RUN/run_report.out" 2>&1 && touch "$RUN/COMPLETE"
  log "ICL: $(tail -1 "$RUN/run_report.out")"
  tar -czf "$INFER/archive/v2/icl/qwen3-vl-8b-thinking.tar.gz" -C "$INFER/real_trials/v2/icl" qwen3-vl-8b-thinking
fi
log "Ministral queue next"
HF_HOME=/var/tmp/lh_robust_tamp_hf QUEUE_OUT=$INFER/real_trials/v2/table2 QUEUE_ARCHIVE=$INFER/archive/v2/table2 \
  "$REPO/server/run_model_queue.sh" ministral-3-8b-instruct ministral-3-8b-reasoning
log "ICL_AND_MINISTRAL_DONE"
