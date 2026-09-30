#!/usr/bin/env bash
# Card-1 previews once the local video recording has finished (2 local simulations at most).
cd /home/naren/iiith/TAMP-PDDL-11-Feb
until grep -q ALL_VIDEOS_DONE results/visuals/videos/record_all.log; do sleep 30; done
export PDDLSTREAM_DIR=$HOME/.cache/tamp_pddl/TAMP-PDDL/pddlstream OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
. mujoco_port/activate_mujoco_env.sh >/dev/null
R=results/figures/fig1_frames/gt_trials
nice -n 10 python tools/figures/render_fig1_frames.py preview --k1w1 $R/FINAL.K1-w1/seed_00 --k4 $R/FINAL.K4/seed_00
echo PREVIEWS_DONE
