#!/usr/bin/env bash
# Planner-model queue (Table 2 on this server): for each profile alias of llm_pipeline/model_profiles.py,
# in order, one model on the GPU at a time:
#   1. make sure its pinned snapshot is on disk (download it if not; the next one is prefetched
#      while the current model runs, when the disk has room);
#   2. serve it (server/start_vllm.sh VLLM_MODEL=<alias>) and record the run manifest;
#   3. run every final variant x seeds 0-9 (full system, zero-shot, 24576 output tokens, the
#      profile's model-card sampling), 6 trials at a time;
#   4. save the vLLM log and metrics, write run_report.{json,md}, check completeness;
#   5. archive the run directory (tar.gz), and only then delete the weights, and only if this
#      project downloaded them (logs/downloaded_models.tsv), no later profile uses them, and the
#      model is not kept (KEEP_REPOS).
# Results (predictions, thinking, action sequences, prompts, images, metrics) are never deleted.
#
#   run_model_queue.sh [alias ...]      (default: model_profiles.RUN_ORDER)
set -uo pipefail
. ~/robust_tamp_infer/sim_env.sh >/dev/null           # simulator env; cd ~/robust_tamp_run
REPO=~/robust_tamp_run
INFER=~/robust_tamp_infer
OUT=${QUEUE_OUT:-$INFER/real_trials/table2}
ARCHIVE=$INFER/archive/table2
export HF_HOME=/home/projects/long-horizon/.cache/huggingface
HUB=$HF_HOME/hub
DL_LOG=$INFER/logs/downloaded_models.tsv
KEEP_REPOS="Qwen/Qwen3-VL-8B-Thinking"                # the selected model, used in all later experiments
VARIANTS="FINAL.K0 FINAL.G0 FINAL.K1 FINAL.K2 FINAL.K3 FINAL.K4 FINAL.G1 FINAL.G2 FINAL.G3 FINAL.K3-n2 FINAL.K3-n3 FINAL.G1-n1 FINAL.K1-w1 FINAL.K1-w2"
SEEDS=0-9
JOBS=${QUEUE_JOBS:-6}
FLAGS="--flag memory.enabled=true --flag replan.trigger_mode=if_rule --flag replan.output_mode=corrective --flag parallel.enabled=true"
COMMON="--remote --remote-api openai --remote-url http://127.0.0.1:8000 --planner-max-new-tokens 24576 --icl-mode zero_shot"
export LLM_REQUEST_TIMEOUT_S=1800                      # per planner call (a timeout is infrastructure, rerun)
PROFILES_PY="python3 $REPO/llm_pipeline/model_profiles.py"
mkdir -p "$OUT" "$ARCHIVE" "$INFER/logs"
log() { echo "[queue $(date -Is)] $*"; }

if [ $# -gt 0 ]; then ALIASES=("$@"); else
  mapfile -t ALIASES < <(python3 -c "import sys; sys.path.insert(0, '$REPO'); from llm_pipeline.model_profiles import RUN_ORDER; print('\n'.join(RUN_ORDER))")
fi
git -C "$REPO" log --oneline -1; git -C "$REPO" status --short -uno
log "queue: ${ALIASES[*]}"

field() { $PROFILES_PY json "$1" | python3 -c "import json,sys; print(json.load(sys.stdin)['$2'])"; }
snapshot_dir() { echo "$HUB/models--$(field "$1" repo | sed 's#/#--#g')/snapshots/$(field "$1" revision)"; }
has_weights() {   # the pinned snapshot with its weights
  local d; d=$(snapshot_dir "$1")
  [ -f "$d/config.json" ] || [ -f "$d/params.json" ] || return 1
  ls "$d"/*.safetensors >/dev/null 2>&1
}
download() {      # $1 alias: hf download of the pinned snapshot (idempotent: completes a partial
                  # download, only verifies a complete one); one download per repo at a time
  local alias=$1 repo existed=0; repo=$(field "$alias" repo)
  local lock="$INFER/logs/.dl_${repo//\//__}.lock"
  exec 9>"$lock"; flock 9
  [ -d "$HUB/models--${repo//\//--}" ] && existed=1
  local args; args=$($PROFILES_PY download "$alias")
  for i in 1 2 3 4 5; do
    log "download $repo (attempt $i)"
    if (unset HF_HUB_OFFLINE; eval timeout 10800 "$INFER/.venv/bin/hf" $args) >> "$INFER/logs/download_${repo//\//__}.log" 2>&1 \
       && has_weights "$alias"; then
      # Weights this project downloaded (and may delete later); a snapshot that was already in
      # the shared cache before this project touched it is never recorded, so never deleted.
      if [ "$existed" = 0 ] && ! grep -q "^$repo	" "$DL_LOG" 2>/dev/null; then
        echo -e "$repo\t$(field "$alias" revision)\t$(du -shL "$(snapshot_dir "$alias")" | cut -f1)\t$(date -Is)\tdownloaded_by_robust_tamp" >> "$DL_LOG"
      fi
      flock -u 9; return 0
    fi
    sleep $((i * 20))
  done
  flock -u 9; return 1
}
disk_free_gb() { df -BG --output=avail /home | tail -1 | tr -dc 0-9; }
prefetch_next() { # download the next two aliases while this one runs, when there is room (~20 GB each + 30 GB margin)
  local after=$1 seen=0 n=0 a
  for a in "${ALIASES[@]}"; do
    if [ "$seen" = 1 ] && [ ! -f "$OUT/$a/COMPLETE" ] && [ "$n" -lt 2 ]; then
      if [ "$(disk_free_gb)" -gt 50 ]; then (download "$a" >/dev/null 2>&1 &) ; log "prefetching $a"; fi
      n=$((n + 1))
    fi
    [ "$a" = "$after" ] && seen=1
  done
}
used_later() {    # does a later alias in the queue use this repo?
  local after=$1 repo=$2 seen=0 a
  for a in "${ALIASES[@]}"; do
    [ "$seen" = 1 ] && [ "$(field "$a" repo)" = "$repo" ] && [ ! -f "$OUT/$a/COMPLETE" ] && return 0
    [ "$a" = "$after" ] && seen=1
  done
  return 1
}

for alias in "${ALIASES[@]}"; do
  run="$OUT/$alias"
  if [ -f "$run/COMPLETE" ]; then log "$alias: already complete"; continue; fi
  mkdir -p "$run"
  repo=$(field "$alias" repo); mtype=$(field "$alias" model_type)
  download "$alias" || { log "$alias: download failed (gated or network); skipped"; echo "download failed" > "$run/SKIPPED"; continue; }
  rm -f "$run/SKIPPED"
  prefetch_next "$alias"
  "$REPO/server/stop_vllm.sh" >/dev/null 2>&1; sleep 5
  if ! VLLM_MODEL="$alias" "$REPO/server/start_vllm.sh" > "$run/start_vllm.out" 2>&1; then
    log "$alias: vLLM did not start (see $run/start_vllm.out and $INFER/logs/vllm_latest.log)"
    cp -L "$INFER/logs/vllm_latest.log" "$run/vllm_server.log" 2>/dev/null
    echo "vllm start failed" > "$run/SKIPPED"; continue
  fi
  # Run manifest: the profile, what the server reports, the serve command, GPU, code.
  python3 - "$alias" "$run" <<'PY'
import json, subprocess, sys, socket, datetime, urllib.request
alias, run = sys.argv[1], sys.argv[2]
def sh(cmd):
    try: return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60).stdout.strip()
    except Exception as e: return f'error: {e}'
def get(path):
    try:
        with urllib.request.urlopen('http://127.0.0.1:8000' + path, timeout=30) as f: return json.load(f)
    except Exception as e: return {'error': str(e)}
repo = '/home/projects/long-horizon/robust_tamp_run'
manifest = {
    'alias': alias, 'started': datetime.datetime.now().astimezone().isoformat(), 'host': socket.gethostname(),
    'profile': json.loads(sh(f'python3 {repo}/llm_pipeline/model_profiles.py json {alias}')),
    'v1_models': get('/v1/models'), 'version': get('/version'),
    'serve_command': sh('cat ~/robust_tamp_infer/logs/serve_command.txt'),
    'gpu': sh('nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader'),
    'git_commit': sh(f'git -C {repo} rev-parse HEAD'), 'git_status': sh(f'git -C {repo} status --short -uno'),
    'run_settings': {'variants': 14, 'seeds': '0-9', 'jobs': None, 'max_new_tokens': 24576, 'icl': 'zero_shot',
                     'flags': 'memory on, IF rule, corrective, parallel on', 'max_model_len': 32768},
}
json.dump(manifest, open(f'{run}/manifest.json', 'w'), indent=1)
PY
  # One call through the planner client (the profile's packaging and sampling), saved in full.
  python - "$alias" "$run" <<'PY' > "$run/smoke.out" 2>&1
import json, sys
import numpy as np
from llm_pipeline.vllm_client import VLLMChatPlanner
alias, run = sys.argv[1], sys.argv[2]
planner = VLLMChatPlanner(model=alias)
assert planner.load_model(), 'server does not serve the profile'
image = np.full((64, 64, 3), 128, dtype=np.uint8) if planner.model_type == 'vlm' else None
out = planner.chat('You are a test harness.', 'Reply with the single word OK.', 2048, image=image)
out.pop('image_png', None)
json.dump({'settings': planner.server_settings, 'call': out}, open(f'{run}/smoke.json', 'w'), indent=1, default=str)
print('SMOKE content=%r finish=%s tokens=%s reasoning_chars=%d' % (out['content'][:80], out['finish_reason'],
      out['completion_tokens'], len(out['reasoning'] or '')))
PY
  log "$alias: $(tail -1 "$run/smoke.out")"
  VISION=""; [ "$mtype" = vlm ] && VISION="--vision"
  log "$alias: running $VARIANTS x $SEEDS ($mtype)"
  nice -n 5 python -m llm_pipeline.run_trial_matrix --planner model --jobs "$JOBS" --timeout 14400 \
    --variants $VARIANTS --seeds "$SEEDS" --out "$run" --title "$alias (zero-shot, full system)" -- \
    --model "$alias" --model-type "$mtype" $VISION $COMMON $FLAGS > "$run/matrix.log" 2>&1
  curl -s --max-time 30 http://127.0.0.1:8000/metrics > "$run/vllm_metrics.prom"
  cp -L "$INFER/logs/vllm_latest.log" "$run/vllm_server.log" 2>/dev/null
  cp "$INFER/logs/serve_command.txt" "$run/serve_command.txt" 2>/dev/null
  python3 -c "import json,datetime; m=json.load(open('$run/manifest.json')); m['finished']=datetime.datetime.now().astimezone().isoformat(); m['run_settings']['jobs']=$JOBS; json.dump(m, open('$run/manifest.json','w'), indent=1)"
  if python -m evaluation.model_run_report "$run" --variants $VARIANTS --seeds "$SEEDS" > "$run/run_report.out" 2>&1; then
    touch "$run/COMPLETE"; log "$alias: complete: $(tail -1 "$run/run_report.out")"
  else
    log "$alias: INCOMPLETE: $(tail -1 "$run/run_report.out"); weights kept"
  fi
  # Archive the results before any deletion; delete only complete, archived, our own, unused-later weights.
  if tar -czf "$ARCHIVE/$alias.tar.gz" -C "$OUT" "$alias" && [ -f "$run/COMPLETE" ]; then
    if echo " $KEEP_REPOS " | grep -q " $repo "; then log "$alias: $repo kept (selected model)";
    elif used_later "$alias" "$repo"; then log "$alias: $repo kept (used by a later profile)";
    elif grep -q "^$repo	.*downloaded_by_robust_tamp" "$DL_LOG" 2>/dev/null; then
      "$REPO/server/stop_vllm.sh" >/dev/null 2>&1; sleep 5
      rm -rf "$HUB/models--${repo//\//--}" && log "$alias: deleted the weights of $repo (results archived: $ARCHIVE/$alias.tar.gz)"
      echo -e "$repo\t$(date -Is)\tdeleted_after_$alias" >> "$INFER/logs/deleted_models.tsv"
    else log "$alias: $repo was not downloaded by this project; kept"; fi
  fi
done
log "QUEUE_DONE"
