#!/usr/bin/env bash
# Main results and ablations with the selected planner (Qwen3-VL-8B-Thinking), then the rest of
# Table 2 (b), all at the placement-fix code. Results: $INFER/real_trials/v2/.
#   table2/qwen3-vl-8b-thinking   full system, all 14 variants x seeds 0-9 (Table 4 "Ours", Table 2 (b))
#   ablations/previous_system     all 14 variants x 0-9 (Table 4 "Previous", Table 5)
#   ablations/<condition>         the 7 core variants x 0-9 (Table 5)
# Then server/run_model_queue.sh for the remaining Table 2 (b) models into v2/table2.
set -uo pipefail
INFER=${QUEUE_INFER:-$HOME/robust_tamp_infer}
. "$INFER/sim_env.sh" >/dev/null
REPO=${QUEUE_REPO:-$HOME/robust_tamp_run}
V2=$INFER/real_trials/v2
ARCHIVE=$INFER/archive/v2
mkdir -p "$V2/ablations" "$V2/table2" "$ARCHIVE"
export LLM_REQUEST_TIMEOUT_S=1800
MODEL=qwen3-vl-8b-thinking
ALL="FINAL.K0 FINAL.G0 FINAL.K1 FINAL.K2 FINAL.K3 FINAL.K4 FINAL.G1 FINAL.G2 FINAL.G3 FINAL.K3-n2 FINAL.K3-n3 FINAL.G1-n1 FINAL.K1-w1 FINAL.K1-w2"
CORE="FINAL.K1 FINAL.K2 FINAL.K3 FINAL.K4 FINAL.G1 FINAL.G2 FINAL.G3"
FULL="--flag memory.enabled=true --flag replan.trigger_mode=if_rule --flag replan.output_mode=corrective --flag replan.insertion_mode=planner --flag parallel.enabled=true"
COMMON="--model $MODEL --model-type vlm --vision --remote --remote-api openai --remote-url http://127.0.0.1:8000 --planner-max-new-tokens 24576 --icl-mode zero_shot"
log() { echo "[v2 $(date -Is)] $*"; }
git -C "$REPO" log --oneline -1; git -C "$REPO" status --short -uno

# name | variants | flags
CONDITIONS=(
  "table2/$MODEL|$ALL|$FULL"
  "ablations/previous_system|$ALL|--flag memory.enabled=false --flag replan.trigger_mode=discovery --flag replan.output_mode=full_replan --flag parallel.enabled=false"
  "ablations/no_memory|$CORE|--flag memory.enabled=false --flag replan.trigger_mode=if_rule --flag replan.output_mode=corrective --flag replan.insertion_mode=planner --flag parallel.enabled=true"
  "ablations/no_if|$CORE|--flag memory.enabled=true --flag replan.trigger_mode=discovery --flag replan.output_mode=corrective --flag replan.insertion_mode=planner --flag parallel.enabled=true"
  "ablations/no_where|$CORE|--flag memory.enabled=true --flag replan.trigger_mode=if_rule --flag replan.output_mode=full_replan --flag parallel.enabled=false"
  "ablations/fixed_front|$CORE|--flag memory.enabled=true --flag replan.trigger_mode=if_rule --flag replan.output_mode=corrective --flag replan.insertion_mode=always_front --flag parallel.enabled=true"
  "ablations/fixed_end|$CORE|--flag memory.enabled=true --flag replan.trigger_mode=if_rule --flag replan.output_mode=corrective --flag replan.insertion_mode=always_end --flag parallel.enabled=true"
  "ablations/no_when|$CORE|--flag memory.enabled=true --flag replan.trigger_mode=if_rule --flag replan.output_mode=corrective --flag replan.insertion_mode=planner --flag parallel.enabled=false"
)

"$REPO/server/stop_vllm.sh" >/dev/null 2>&1; sleep 5
VLLM_MODEL=$MODEL "$REPO/server/start_vllm.sh" || { log "vLLM did not start"; exit 1; }
for entry in "${CONDITIONS[@]}"; do
  IFS='|' read -r name variants flags <<< "$entry"
  run="$V2/$name"
  if [ -f "$run/COMPLETE" ]; then log "$name: already complete"; continue; fi
  mkdir -p "$run"
  python3 - "$run" "$REPO" "$INFER" "$name" "$variants" "$flags" <<'PY'
import json, subprocess, sys, socket, datetime, urllib.request
run, repo, infer, name, variants, flags = sys.argv[1:7]
sh = lambda c: subprocess.run(c, shell=True, capture_output=True, text=True).stdout.strip()
def get(p):
    try:
        with urllib.request.urlopen('http://127.0.0.1:8000' + p, timeout=30) as f: return json.load(f)
    except Exception as e: return {'error': str(e)}
json.dump({'condition': name, 'variants': variants.split(), 'seeds': '0-9', 'flags': flags.split(),
           'model_profile': json.loads(sh(f'python3 {repo}/llm_pipeline/model_profiles.py json qwen3-vl-8b-thinking')),
           'v1_models': get('/v1/models'), 'version': get('/version'), 'serve_command': sh(f'cat {infer}/logs/serve_command.txt'),
           'gpu': sh('nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader'),
           'git_commit': sh(f'git -C {repo} rev-parse HEAD'), 'git_status': sh(f'git -C {repo} status --short -uno'),
           'host': socket.gethostname(), 'started': datetime.datetime.now().astimezone().isoformat(),
           'max_new_tokens': 24576, 'icl': 'zero_shot', 'jobs': 6}, open(f'{run}/manifest.json', 'w'), indent=1)
PY
  log "$name: running ($variants)"
  nice -n 5 python -m llm_pipeline.run_trial_matrix --planner model --jobs 6 --timeout 14400 --variants $variants \
    --seeds 0-9 --out "$run" --title "$name ($MODEL, zero-shot)" -- $COMMON $flags > "$run/matrix.log" 2>&1
  curl -s --max-time 30 http://127.0.0.1:8000/metrics > "$run/vllm_metrics.prom"
  if python -m evaluation.model_run_report "$run" --variants $variants --seeds 0-9 > "$run/run_report.out" 2>&1; then
    touch "$run/COMPLETE"; log "$name: complete: $(tail -1 "$run/run_report.out")"
  else
    log "$name: INCOMPLETE: $(tail -1 "$run/run_report.out")"
  fi
  tar -czf "$ARCHIVE/${name//\//__}.tar.gz" -C "$V2" "$name"
done
cp -L "$INFER/logs/vllm_latest.log" "$V2/ablations/vllm_server_$MODEL.log" 2>/dev/null
log "main results and ablations done; Table 2 (b) queue next"
QUEUE_OUT="$V2/table2" QUEUE_ARCHIVE="$ARCHIVE/table2" "$REPO/server/run_model_queue.sh" \
  qwen3-8b holo2-8b internvl3.5-8b qwen2.5-7b-instruct r1-distill-qwen-7b r1-distill-llama-8b \
  ministral-3-8b-instruct ministral-3-8b-reasoning llama-3.1-8b-instruct
log "V2_ALL_DONE"
