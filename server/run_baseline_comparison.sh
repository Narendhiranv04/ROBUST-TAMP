#!/usr/bin/env bash
# External baselines (baselines/: vlm_tamp, owl_tamp, llm_planner, inner_monologue) with the selected planner model, every variant
# x seeds, on one vLLM server: the comparison rows of the paper.
#
#   BASELINE_OUT=<dir> server/run_baseline_comparison.sh [baselines] [seeds]
#
# Defaults: both baselines, seeds 0-9, all 14 final variants, 6 trials at a time, the model profile
# qwen3-vl-8b-thinking (card sampling, 24,576 output tokens). Each trial goes to
# $BASELINE_OUT/<baseline>/<variant>/seed_XX (trial_log.jsonl, record.json, prompts with every
# request/response and image); a trial that ends as infrastructure (server error, simulator error)
# is moved to seed_XX.infra_attemptN and rerun, at most 3 attempts. Then a run report per baseline
# (evaluation/model_run_report.py), COMPLETE when every trial has a scored result, and an archive.
# BASELINE_RERUN_EXECUTION_FAILURES=1 first moves the failed executions of an earlier run (shared
# working directory, baselines/execution_failures.py) to seed_XX.shared_temp, so they are re-run.
# BASELINE_RERUN_VARIANTS="<variants>" BASELINE_RERUN_TAG=<tag>: every trial of these variants is
# moved to seed_XX.<tag> and re-run (code changed for them).
# BASELINE_RERUN_FILE=<file of "<variant> <seed>" lines> BASELINE_RERUN_TAG=<tag>: those trials likewise.
# BASELINE_REUSE_VLLM=1: use the vLLM server already serving the profile's model (two queues on one machine).
# BASELINE_ICL_MODE=examples_v2: the in-context examples of our ICL condition, in each baseline's format (grill
# scene only, baselines/icl_examples.py); run it with BASELINE_VARIANTS set to the grill variants.
set -uo pipefail
INFER=${QUEUE_INFER:-$HOME/robust_tamp_infer}
REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
. "$INFER/sim_env.sh" >/dev/null
# sim_env.sh activates the main checkout; this run uses its own (the scripts' checkout)
cd "$REPO" && . mujoco_port/activate_mujoco_env.sh >/dev/null
OUT=$(realpath -m "${BASELINE_OUT:?set BASELINE_OUT}")
ARCHIVE=${BASELINE_ARCHIVE:-$OUT/archive}
MODEL=${BASELINE_MODEL:-qwen3-vl-8b-thinking}
JOBS=${BASELINE_JOBS:-6}
ICL_MODE=${BASELINE_ICL_MODE:-zero_shot}
BASELINES=${1:-"vlm_tamp owl_tamp"}
SEEDS=${2:-"0 1 2 3 4 5 6 7 8 9"}
VARIANTS=${BASELINE_VARIANTS:-"FINAL.K0 FINAL.G0 FINAL.K1 FINAL.K2 FINAL.K3 FINAL.K4 FINAL.G1 FINAL.G2 FINAL.G3 FINAL.K3-n2 FINAL.K3-n3 FINAL.G1-n1 FINAL.K1-w1 FINAL.K1-w2"}
export LLM_REQUEST_TIMEOUT_S=1800
mkdir -p "$OUT" "$ARCHIVE"
log() { echo "[baselines $(date -Is)] $*"; }
cd "$REPO"
log "code $(git log --oneline -1)"; git status --short -uno

# the model: the pinned snapshot (downloaded only if missing), then serve it
export HF_HOME=${HF_HOME:-/home/projects/long-horizon/.cache/huggingface}
eval "$(python3 llm_pipeline/model_profiles.py shell "$MODEL")"
if [ ! -f "$HF_HOME/hub/models--${MODEL_REPO//\//--}/snapshots/$MODEL_REVISION/config.json" ]; then
  (unset HF_HUB_OFFLINE; eval "$INFER/.venv/bin/hf" $(python3 llm_pipeline/model_profiles.py download "$MODEL")) \
    > "$OUT/download.log" 2>&1 || { log "download failed"; exit 1; }
fi
if [ -n "${BASELINE_REUSE_VLLM:-}" ] && curl -s --max-time 30 http://127.0.0.1:8000/v1/models | grep -q "\"id\":\"$MODEL\""; then
  # another queue on this machine started the server: share it (no restart)
  log "reusing the running vLLM server ($MODEL)"; echo "reused" > "$OUT/start_vllm.out"
else
  "$REPO/server/stop_vllm.sh" >/dev/null 2>&1; sleep 10
  VLLM_MODEL=$MODEL "$REPO/server/start_vllm.sh" > "$OUT/start_vllm.out" 2>&1 || { log "vLLM did not start"; exit 1; }
fi
python3 - "$OUT" "$REPO" "$INFER" "$MODEL" "$BASELINES" "$SEEDS" "$VARIANTS" "$JOBS" "$ICL_MODE" <<'PY'
import json, subprocess, sys, socket, datetime, urllib.request
out, repo, infer, model, baselines, seeds, variants, jobs, icl_mode = sys.argv[1:10]
sh = lambda c: subprocess.run(c, shell=True, capture_output=True, text=True).stdout.strip()
def get(p):
    try:
        with urllib.request.urlopen('http://127.0.0.1:8000' + p, timeout=30) as f: return json.load(f)
    except Exception as e: return {'error': str(e)}
json.dump({'baselines': baselines.split(), 'icl_mode': icl_mode, 'variants': variants.split(), 'seeds': seeds.split(), 'jobs': int(jobs),
           'model_profile': json.loads(sh(f'python3 {repo}/llm_pipeline/model_profiles.py json {model}')),
           'v1_models': get('/v1/models'), 'version': get('/version'), 'serve_command': sh(f'cat {infer}/logs/serve_command.txt'),
           'gpu': sh('nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader'),
           'git_commit': sh(f'git -C {repo} rev-parse HEAD'), 'git_status': sh(f'git -C {repo} status --short -uno'),
           'host': socket.gethostname(), 'started': datetime.datetime.now().astimezone().isoformat(),
           'max_new_tokens': 24576}, open(f'{out}/manifest.json', 'w'), indent=1)
PY

# one trial, with infrastructure reruns
trial() {
  local b=$1 v=$2 s=$3 dir attempt end cwd
  dir="$OUT/$b/$v/seed_$(printf %02d "$s")"
  for attempt in 1 2 3; do
    if [ -f "$dir/trial_log.jsonl" ] && grep -q '"event": "trial_end"' "$dir/trial_log.jsonl" \
       && ! grep '"event": "trial_end"' "$dir/trial_log.jsonl" | grep -q '"termination_reason": "infrastructure"'; then
      return 0                                            # already scored (resume)
    fi
    [ -d "$dir" ] && mv "$dir" "$dir.infra_attempt$(ls -d "$dir".infra_attempt* 2>/dev/null | wc -l | awk '{print $1+1}')"
    mkdir -p "$dir"
    # each trial in its own working directory, as in llm_pipeline/run_trial_matrix.py: FastDownward
    # writes temp/ under the working directory, shared by the parallel trials otherwise
    cwd=$(mktemp -d "${TMPDIR:-/tmp}/baseline_${b}_${v}_${s}_XXXXXX")
    (cd "$cwd" && nice -n 5 timeout 14400 python3 -m baselines.run_baseline_trial --baseline "$b" --variant "$v" \
      --seed "$s" --output-dir "$dir" --model "$MODEL" --remote-url http://127.0.0.1:8000 --attempt "$attempt" --icl-mode "$ICL_MODE") \
      > "$dir/stdout.log" 2>&1
    rm -rf "$cwd"
    end=$(grep '"event": "trial_end"' "$dir/trial_log.jsonl" 2>/dev/null | tail -1)
    echo "[trial] $b $v seed $s attempt $attempt: $(echo "$end" | python3 -c 'import sys,json; l=sys.stdin.read().strip(); e=json.loads(l) if l else {}; print(json.dumps({k: e.get(k) for k in ("success","partial_goal_completion","planner_calls","termination_reason")}))')"
    if [ -n "$end" ] && ! echo "$end" | grep -q '"termination_reason": "infrastructure"'; then return 0; fi
  done
}
export -f trial log
export OUT MODEL ICL_MODE

for b in $BASELINES; do
  if [ -n "${BASELINE_RERUN_EXECUTION_FAILURES:-}" ] && [ -d "$OUT/$b" ]; then
    # a run made before each trial had its own working directory: re-run its failed executions
    python3 -m baselines.execution_failures "$OUT/$b" > "$OUT/$b.shared_temp_reruns.txt"
    log "$b: re-running $(wc -l < "$OUT/$b.shared_temp_reruns.txt") trials whose execution failed (shared temp/)"
    for f in run_report.out matrix.log COMPLETE; do [ -e "$OUT/$b.$f" ] && cp "$OUT/$b.$f" "$OUT/$b.$f.before_shared_temp_reruns"; done
    rm -f "$OUT/$b.COMPLETE"
    while read -r v s; do
      d="$OUT/$b/$v/seed_$(printf %02d "$s")"; mv "$d" "$d.shared_temp"
    done < "$OUT/$b.shared_temp_reruns.txt"
  fi
  if [ -n "${BASELINE_RERUN_VARIANTS:-}" ] && [ -d "$OUT/$b" ]; then
    # changed code for these variants: re-run every trial of them (earlier ones kept as seed_XX.<tag>)
    tag=${BASELINE_RERUN_TAG:?set BASELINE_RERUN_TAG with BASELINE_RERUN_VARIANTS}
    for f in run_report.out matrix.log COMPLETE; do [ -e "$OUT/$b.$f" ] && cp "$OUT/$b.$f" "$OUT/$b.$f.before_$tag"; done
    rm -f "$OUT/$b.COMPLETE"
    for v in $BASELINE_RERUN_VARIANTS; do for s in $SEEDS; do
      d="$OUT/$b/$v/seed_$(printf %02d "$s")"; [ -d "$d" ] && mv "$d" "$d.$tag"
    done; done
    log "$b: re-running every trial of $BASELINE_RERUN_VARIANTS (earlier trials: seed_XX.$tag)"
  fi
  if [ -n "${BASELINE_RERUN_FILE:-}" ] && [ -d "$OUT/$b" ]; then
    # changed code for these trials ("<variant> <seed>" lines): re-run them (earlier: seed_XX.<tag>)
    tag=${BASELINE_RERUN_TAG:?set BASELINE_RERUN_TAG with BASELINE_RERUN_FILE}
    cp "$BASELINE_RERUN_FILE" "$OUT/$b.$tag.txt"
    for f in run_report.out matrix.log COMPLETE; do [ -e "$OUT/$b.$f" ] && cp "$OUT/$b.$f" "$OUT/$b.$f.before_$tag"; done
    rm -f "$OUT/$b.COMPLETE"
    while read -r v s; do
      d="$OUT/$b/$v/seed_$(printf %02d "$s")"; [ -d "$d" ] && mv "$d" "$d.$tag"
    done < "$OUT/$b.$tag.txt"
    log "$b: re-running $(wc -l < "$OUT/$b.$tag.txt") listed trials (earlier trials: seed_XX.$tag)"
  fi
  log "$b: running $(echo $VARIANTS | wc -w) variants x seeds [$SEEDS], $JOBS at a time"
  for s in $SEEDS; do for v in $VARIANTS; do echo "$b $v $s"; done; done \
    | xargs -P "$JOBS" -L 1 bash -c 'trial "$0" "$1" "$2"' >> "$OUT/$b.matrix.log" 2>&1
  curl -s --max-time 30 http://127.0.0.1:8000/metrics > "$OUT/$b.vllm_metrics.prom"
  seeds_range="$(echo $SEEDS | awk '{print $1"-"$NF}')"
  if python3 -m evaluation.model_run_report "$OUT/$b" --variants $VARIANTS --seeds "$seeds_range" > "$OUT/$b.run_report.out" 2>&1; then
    touch "$OUT/$b.COMPLETE"; log "$b: complete: $(tail -1 "$OUT/$b.run_report.out")"
  else
    log "$b: INCOMPLETE: $(tail -1 "$OUT/$b.run_report.out")"
  fi
  tar -czf "$ARCHIVE/$b.tar.gz" -C "$OUT" "$b" "$b.matrix.log" "$b.run_report.out" 2>/dev/null
done
cp -L "$INFER/logs/vllm_latest.log" "$OUT/vllm_server.log" 2>/dev/null
log "BASELINES_DONE"
