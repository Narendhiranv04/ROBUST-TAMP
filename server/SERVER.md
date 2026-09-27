# ROBUST TAMP inference server (gvlab2)

Planner model server for ROBUST TAMP: vLLM serving **Qwen3-VL-8B-Thinking** through an OpenAI-compatible API, plus a headless copy of the simulator for oracle and model trials. Set up on 2026-09-26/27.

- **Access:** `ssh -i ~/keyfile long-horizon@gvlab2.iiit.ac.in`. The login shell is fish, so always wrap commands: `"bash -lc '<command>'"`.
- **DNS:** the server's DNS is intermittently flaky; retry network commands up to 5 times.
- **Code:** the server has no GitHub access. Code arrives through the bare repo `~/robust_tamp.git`, cloned at `~/robust_tamp_run`.

## Hardware (host `cstar`)

| | |
|---|---|
| GPU | 1 × NVIDIA GeForce RTX 5090, 32 GB (32607 MiB), compute capability 12.0. It was idle before setup. |
| Driver / CUDA | Driver 580.95.05 (CUDA 13.0); CUDA toolkit 13.0.88 at `/usr/local/cuda` |
| CPU | AMD Ryzen Threadripper 7960X: 24 cores, 48 threads |
| RAM | 125 GB, plus 31 GB swap |
| Disk | `/` is 424 GB with 307 GB free. `/home` is 1.8 TB with 159 GB free; the HF cache is here. |
| OS | Ubuntu 24.04.3 LTS; `uv` 0.9.10; `tmux` |

There is only one GPU, so tensor parallelism is 1. `start_vllm.sh` uses every visible GPU if more are added.

## Software

**vLLM environment:** `~/robust_tamp_infer/.venv` (uv, Python 3.12.3, isolated).

| Package | Version |
|---|---|
| vllm | 0.30.0 (latest release, 2026-09-22) |
| torch | 2.13.0+cu130 (CUDA 13.0) |
| transformers | 5.17.0 |
| flashinfer-python | 0.6.18.post1 |

Install script: `install_env.sh`, which runs `uv pip install "vllm==0.30.0" --torch-backend=auto`.

**Simulator environment:** `~/robust_tamp_simenv` (uv, Python 3.13.9), separate from vLLM. The versions mirror the validated local setup:

| Package | Version |
|---|---|
| mujoco | 3.10.0 |
| numpy | 2.4.0 (PyPI marks this release as yanked; it is kept to match the validated setup) |
| scipy | 1.16.3 |
| pillow | 12.0.0 |
| opencv-python-headless | 5.0.0 |
| trimesh | 5.0.0 |
| pytest | 9.1.1 |

Also installed: requests, pydantic, matplotlib, pyyaml, networkx, imageio, tqdm. Install script: `install_sim_env.sh`.

## Model

| | |
|---|---|
| Hugging Face repo | `Qwen/Qwen3-VL-8B-Thinking` (checked against the Hub API: pipeline `image-text-to-text`) |
| Revision (pinned) | **`92f3c4b4feadd3a016ef468d103bb5f58b2a2c6b`** (Hub `main` on 2026-09-26, last modified 2025-11-26) |
| Weights | bf16, 4 safetensors shards, 17 GB. `Qwen3VLForConditionalGeneration`; native context 262144. |
| Cache | `HF_HOME=/home/projects/long-horizon/.cache/huggingface` (on `/home`, the largest disk; shared with the account's other models) |

The pinned download is resumable and was verified complete: `hf download Qwen/Qwen3-VL-8B-Thinking --revision 92f3c4b4…`, log in `logs/download.log`. Serving runs with `HF_HUB_OFFLINE=1`, so start-up never needs the network.

### Recommended thinking-mode sampling
Source: the model card, section "Generation Hyperparameters", and `generation_config.json`. Use exactly these values.

| Setting | Vision-language (VL) | Text-only |
|---|---|---|
| temperature | 1.0 | 1.0 |
| top_p | 0.95 | 0.95 |
| top_k | 20 | 20 |
| repetition_penalty | 1.0 | 1.0 |
| presence_penalty | **0.0** | **1.5** |
| min_p | not specified (vLLM default 0.0) | not specified |
| greedy | false (sampling) | false |
| recommended output length | 40960 | 32768 (81920 for AIME/LCB/GPQA) |

`generation_config.json` has `do_sample=true, temperature=1.0, top_p=0.95, top_k=20, repetition_penalty=1.0`. The server runs with `--generation-config auto`, so these are also vLLM's per-request defaults. Clients should still send every value explicitly.

Two limits to be aware of:
- The recommended output lengths are longer than the served context (32768 tokens, prompt included). A client must cap `max_tokens` so that the prompt plus the output fits. ROBUST TAMP's planner requests use `max_new_tokens=24576` (the trial runner default). A sweep on K0, K1 and K3 with 2 seeds each found 8192 cut 3 of 26 answers off mid-thought (5/6 success), while 16384 and 24576 cut none off (6/6); the longest answer seen was 10193 tokens. The non-thinking Qwen3-VL-8B-Instruct went 0/18 on the same trials at every limit.
- Thinking is on by default in the chat template. Send `chat_template_kwargs: {"enable_thinking": true}` explicitly anyway.

## Serving

Scripts in `~/robust_tamp_infer/`:
- **`start_vllm.sh`** is idempotent:
  - it does nothing if the server already answers or its tmux window exists;
  - it refuses if port 8000 is taken by another process;
  - it starts vLLM in tmux session `vllm`, window `serve`, and waits until `/v1/models` answers;
  - logs go to `logs/vllm_<timestamp>.log`, with `logs/vllm_latest.log` pointing at the newest.
- **`stop_vllm.sh`** sends Ctrl-C to that window and closes it. It touches nothing else.

Exact serve command (`logs/serve_command.txt`):
```sh
export HF_HOME=/home/projects/long-horizon/.cache/huggingface HF_HUB_OFFLINE=1 CUDA_HOME=/usr/local/cuda
export PATH=~/robust_tamp_infer/.venv/bin:/usr/local/cuda/bin:$PATH   # flashinfer JIT needs ninja + nvcc
~/robust_tamp_infer/.venv/bin/vllm serve \
  /home/projects/long-horizon/.cache/huggingface/hub/models--Qwen--Qwen3-VL-8B-Thinking/snapshots/92f3c4b4feadd3a016ef468d103bb5f58b2a2c6b \
  --served-model-name qwen3-vl-8b-thinking \
  --host 127.0.0.1 --port 8000 \
  --tensor-parallel-size 1 \
  --max-model-len 32768 \
  --gpu-memory-utilization 0.90 \
  --reasoning-parser qwen3 \
  --limit-mm-per-prompt '{"image": 2, "video": 0}' \
  --generation-config auto
```
Every flag was checked against `vllm serve --help=all` for 0.30.0; the saved output is `logs/serve_help.txt`. `qwen3` is in vLLM's reasoning-parser registry: thinking goes to `reasoning_content` and the answer to `content`.

**What the server runs with:**
- Max context: **32768** tokens, the target. KV cache 8.49 GiB = **61,856 tokens**, i.e. 1.89 requests at full length at once; shorter requests batch more.
- Model weights: 16.65 GiB on the GPU.
- Attention backend: FLASH_ATTN, also used for the vision encoder.
- GPU memory in use while serving: about 27.1 GB of 32.6 GB.

**Start-up problem found and fixed:** at warm-up, flashinfer JIT-compiles its top-k/top-p sampling kernel. Inside tmux, the venv was not on `PATH`, so this failed with `FileNotFoundError: 'ninja'`. `start_vllm.sh` now exports the venv `bin`, `/usr/local/cuda/bin` and `CUDA_HOME`.

**Local access (tunnel):**
```sh
ssh -i ~/keyfile -N -L 8000:127.0.0.1:8000 long-horizon@gvlab2.iiit.ac.in
curl http://127.0.0.1:8000/v1/models
```

**Integration (Phase 7c):** the pipeline talks to this server directly: `python -m llm_pipeline.trial_runner --remote --model qwen3-vl-8b-thinking --remote-url http://127.0.0.1:8000 ...` (default `--remote-api openai`; `llm_pipeline/vllm_client.py`). The script serves the pinned snapshot **directory** (not the repo id), so `GET /v1/models` reports `root = .../snapshots/<revision>`: the client reads the revision from it and refuses a trial if it differs from the pinned one (`vllm_client.PINNED_MODELS`), and re-checks it before every call.

## Health checks (2026-09-27, `health_check.py`, output in `logs/health_check.json`)

All requests used `enable_thinking: true` and the recommended sampling (text settings for the text requests, VL settings for the image request).

| Check | Result |
|---|---|
| `GET /v1/models` | `["qwen3-vl-8b-thinking"]` |
| `GET /version` | `0.30.0` |
| Text completion | `finish_reason=stop`, 3.19 s, 29 prompt + 307 completion tokens, **96.3 tok/s**, reasoning 1285 chars in `reasoning_content`; the answer in `content` is one sentence |
| One base64 image (448×336 PNG, a red square on the left and a blue circle on the right), VL settings | `finish_reason=stop`, 1.20 s, 173 prompt + 113 completion tokens, **94.0 tok/s**, reasoning 258 chars; content: "1. The shape on the left is a **square** with **red** color. 2. The shape on the right is a **circle** with **blue** color." (correct) |
| 4 concurrent requests (text, `max_tokens` 1024) | wall 7.25 s vs 20.6 s summed latency, **260 tok/s aggregate** (about 91 tok/s each), all `stop`; the vLLM log shows `Running: 4 reqs` (batched) |
| Peak GPU memory | **27,114 MiB** of 32,607 MiB |

## Simulator on this server (`~/robust_tamp_run`, branch `phase-7b-fixes`, commit `563beb6`, clean)

- **Environment:** `. ~/robust_tamp_infer/sim_env.sh` does the following:
  - puts `~/robust_tamp_simenv/bin` on `PATH`;
  - sets `PDDLSTREAM_DIR=~/TAMP-PDDL/pddlstream` (its FastDownward build is ready; the Python sources are byte-identical to the validated local copy; the repo's own `pddlstream/` submodule is empty);
  - sets `MUJOCO_GL=egl` and one BLAS thread;
  - sources `mujoco_port/activate_mujoco_env.sh`.
- **Headless rendering:** MuJoCo EGL on the RTX 5090 works. `render_check.py` renders every camera of `final_K1` and `final_G2` non-blank (pixel std 56–80). OSMesa is not installed and not needed.
- **Tests:** `python -m pytest -p no:cacheprovider -q llm_pipeline/tests diagnostics/tests mujoco_port/tests` gives **299 passed** in 9.1 s.
- **Oracle trials** (`llm_pipeline.oracle_trial_runner`, seed 0, default flags, run concurrently from separate working directories):

| Variant | Result | Trial time | Wall time | Peak RSS | CPU |
|---|---|---|---|---|---|
| FINAL.K1 | success, `plan_completed`, 2 planner calls | 79.5 s | 80.6 s | 4.0 GB | 1 core |
| FINAL.G2 | success, `plan_completed`, 2 planner calls | 82.5 s | 84.2 s | 3.8 GB | 1 core |

  Outputs are in `~/robust_tamp_infer/sim_trials/`. Both logs record commit `563beb6`, `dirty: false`.
- **Parallel simulations (estimate):**
  - Each simulation uses about 1 core and about 4 GB RAM.
  - With vLLM running (about 5.7 GB RAM, 27 GB GPU), 116 GB RAM and 24 physical cores are left. That allows about **20 simulations at once** by CPU and about 25 by RAM.
  - EGL render contexts share the GPU's remaining ~5.5 GB; the GPU memory of a context was too small to measure.
  - Recommendation: start at 8 parallel simulations, watch `nvidia-smi` and `free`, then scale up.
  - Run each simulation from its own working directory, because pddlstream writes `./temp`.

## Files
- `start_vllm.sh`, `stop_vllm.sh`: serving.
- `health_check.py`: the checks above.
- `render_check.py`: the EGL camera check.
- `install_env.sh`, `install_sim_env.sh`: the two environments.
- `sim_env.sh`: the simulator shell environment.
- `logs/`: install logs, the vLLM logs, `serve_command.txt`, `serve_help.txt`, `health_check.json`.
