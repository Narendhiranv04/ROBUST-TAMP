#!/usr/bin/env bash
# Back up the planner-model runs from the lab server to this machine, then rebuild Table 2 and
# Figures 4-5 from the copy. Runs every INTERVAL seconds (default 1800) until stopped.
#
#   server/backup_from_server.sh            # loop (start detached: see below)
#   server/backup_from_server.sh --once     # one pass
#   start:  setsid nohup server/backup_from_server.sh > results/table2_backup.log 2>&1 &
#   stop:   kill "$(cat results/.table2_backup.pid)"
#
# Everything is copied except the per-call PNG images (the local disk is small); the images stay
# on the server, which also keeps a .tar.gz of every finished run (~/robust_tamp_infer/archive/).
# rsync never deletes local files (no --delete), so a copy survives anything on the server.
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$REPO/results/table2_runs"
TABLES="$REPO/results/table2"
HOST=long-horizon@gvlab2.iiit.ac.in
SRC=robust_tamp_infer/real_trials/table2/
INTERVAL=${INTERVAL:-1800}
MIN_FREE_MB=${MIN_FREE_MB:-1024}
mkdir -p "$DEST" "$TABLES"
echo $$ > "$REPO/results/.table2_backup.pid"

pass() {
  local free; free=$(df -Pm "$DEST" | awk 'NR==2 {print $4}')
  if [ "$free" -lt "$MIN_FREE_MB" ]; then echo "[backup $(date -Is)] only ${free} MB free; skipped"; return; fi
  for i in 1 2 3 4 5; do
    if rsync -a --partial --exclude='*.png' -e "ssh -i $HOME/keyfile -o ConnectTimeout=20 -o BatchMode=yes" \
         "$HOST:$SRC" "$DEST/"; then
      echo "[backup $(date -Is)] synced: $(find "$DEST" -name record.json | wc -l) trials, $(du -sh "$DEST" | cut -f1)"
      (cd "$REPO" && python3 -m evaluation.table2 --results "$DEST" --out "$TABLES" > "$TABLES/build.log" 2>&1) \
        && (cd "$REPO" && python3 -m evaluation.failure_breakdown --results "$DEST" --out "$TABLES/failures" > /dev/null 2>&1) \
        && echo "[backup $(date -Is)] Table 2, figures and failure breakdown rebuilt in $TABLES" \
        || echo "[backup $(date -Is)] table build failed (see $TABLES/build.log)"
      return
    fi
    sleep $((i * 15))
  done
  echo "[backup $(date -Is)] rsync failed after 5 attempts"
}

if [ "${1:-}" = --once ]; then pass; exit 0; fi
while true; do pass; sleep "$INTERVAL"; done
