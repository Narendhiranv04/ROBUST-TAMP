#!/usr/bin/env bash
# Table 5 with the grill in-context examples (icl_mode examples_v2). The examples reach only the
# grill prompt, so the kitchen trials of v2/ablations/<condition> are unchanged; this reruns the
# grill core variants (G1, G2, G3 x seeds 0-9) of every ablation with ICL, then the LLM-planner
# row (Qwen3-8B, full system). The full-system row is v2/icl/qwen3-vl-8b-thinking.
#   ablations_icl/<condition>       the 6 ablations, Qwen3-VL-8B-Thinking
#   ablations_icl/qwen3-8b-icl      LLM planner (server/run_model_queue.sh)
set -uo pipefail
INFER=${QUEUE_INFER:-$HOME/robust_tamp_infer}
. "$INFER/sim_env.sh" >/dev/null
REPO=${QUEUE_REPO:-$HOME/robust_tamp_run}
V2=$INFER/real_trials/v2
OUTD=$V2/ablations_icl
ARCHIVE=$INFER/archive/v2
mkdir -p "$OUTD" "$ARCHIVE"
export LLM_REQUEST_TIMEOUT_S=1800
MODEL=qwen3-vl-8b-thinking
ICL=examples_v2
GRILL="FINAL.G1 FINAL.G2 FINAL.G3"
COMMON="--model $MODEL --model-type vlm --vision --remote --remote-api openai --remote-url http://127.0.0.1:8000 --planner-max-new-tokens 24576 --icl-mode $ICL"
log() { echo "[abl_icl $(date -Is)] $*"; }
git -C "$REPO" log --oneline -1; git -C "$REPO" status --short -uno

# name | flags (as in server/run_v2_main.sh)
CONDITIONS=(
  "no_memory|--flag memory.enabled=false --flag replan.trigger_mode=if_rule --flag replan.output_mode=corrective --flag replan.insertion_mode=planner --flag parallel.enabled=true"
  "no_if|--flag memory.enabled=true --flag replan.trigger_mode=discovery --flag replan.output_mode=corrective --flag replan.insertion_mode=planner --flag parallel.enabled=true"
  "no_where|--flag memory.enabled=true --flag replan.trigger_mode=if_rule --flag replan.output_mode=full_replan --flag parallel.enabled=false"
  "fixed_front|--flag memory.enabled=true --flag replan.trigger_mode=if_rule --flag replan.output_mode=corrective --flag replan.insertion_mode=always_front --flag parallel.enabled=true"
  "fixed_end|--flag memory.enabled=true --flag replan.trigger_mode=if_rule --flag replan.output_mode=corrective --flag replan.insertion_mode=always_end --flag parallel.enabled=true"
  "no_when|--flag memory.enabled=true --flag replan.trigger_mode=if_rule --flag replan.output_mode=corrective --flag replan.insertion_mode=planner --flag parallel.enabled=false"
)

"$REPO/server/stop_vllm.sh" >/dev/null 2>&1; sleep 5
VLLM_MODEL=$MODEL "$REPO/server/start_vllm.sh" || { log "vLLM did not start"; exit 1; }
for entry in "${CONDITIONS[@]}"; do
  IFS='|' read -r name flags <<< "$entry"
  run="$OUTD/$name"
  if [ -f "$run/COMPLETE" ]; then log "$name: already complete"; continue; fi
  mkdir -p "$run"
  python3 - "$run" "$REPO" "$INFER" "$name" "$GRILL" "$flags" <<'PY'
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
           'max_new_tokens': 24576, 'icl': 'examples_v2', 'jobs': 6}, open(f'{run}/manifest.json', 'w'), indent=1)
PY
  log "$name: running ($GRILL)"
  nice -n 5 python -m llm_pipeline.run_trial_matrix --planner model --jobs 6 --timeout 14400 --variants $GRILL \
    --seeds 0-9 --out "$run" --title "ablations_icl/$name ($MODEL, $ICL)" -- $COMMON $flags > "$run/matrix.log" 2>&1
  curl -s --max-time 30 http://127.0.0.1:8000/metrics > "$run/vllm_metrics.prom"
  if python -m evaluation.model_run_report "$run" --variants $GRILL --seeds 0-9 > "$run/run_report.out" 2>&1; then
    touch "$run/COMPLETE"; log "$name: complete: $(tail -1 "$run/run_report.out")"
  else
    log "$name: INCOMPLETE: $(tail -1 "$run/run_report.out")"
  fi
  tar -czf "$ARCHIVE/ablations_icl__$name.tar.gz" -C "$V2" "ablations_icl/$name"
done
cp -L "$INFER/logs/vllm_latest.log" "$OUTD/vllm_server_$MODEL.log" 2>/dev/null
log "ablations done; LLM planner row next"
HF_HOME=${ABL_LLM_HF_HOME:-/var/tmp/lh_robust_tamp_hf} QUEUE_OUT="$OUTD" QUEUE_ARCHIVE="$ARCHIVE/ablations_icl" QUEUE_ICL=$ICL QUEUE_SUFFIX=-icl QUEUE_VARIANTS="$GRILL" \
  "$REPO/server/run_model_queue.sh" qwen3-8b
log "ABLATIONS_ICL_DONE"
