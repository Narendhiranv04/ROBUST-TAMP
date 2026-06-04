# Model Server Setup For Benchmark Runs

This doc is the stable setup plan for the actual benchmark set. Do not try to make one Python environment serve every model. Keep separate environments for normal LLMs, AWQ LLMs, and newer VLM/FP8 models.

## Benchmark Model Set

### LLMs

| Alias | Model path | Preferred server | Env |
|---|---|---|---|
| `llama-3.3-70b-awq` | `casperhansen/llama-3.3-70b-instruct-awq` | `spectre` | AWQ LLM |
| `deepseek-r1-qwen-32b` | `casperhansen/deepseek-r1-distill-qwen-32b-awq` | `spectre` | AWQ LLM |
| `qwen3.6-27b` / FP8 snapshot | `Qwen/Qwen3.6-27B` or FP8 snapshot | `cstar` for FP8, `spectre` if full/AWQ | New/source LLM |
| `deepseek-r1-qwen-14b` | `deepseek-ai/DeepSeek-R1-Distill-Qwen-14B` | either | Standard LLM |
| `qwen3-8b` | `Qwen/Qwen3-8B` | either | Standard LLM |

### VLMs

| Alias | Model path | Preferred server | Env |
|---|---|---|---|
| `qwen2.5-vl-72b-awq` | `Qwen/Qwen2.5-VL-72B-Instruct-AWQ` | larger/multi-GPU if available, otherwise `spectre` experiment | AWQ VLM / experimental |
| `internvl-3.5-38b` | `OpenGVLab/InternVL3_5-38B` | `cstar` if quantized/fits, otherwise larger GPU | New VLM |
| `llama-3.2-11b-vision` | `meta-llama/Llama-3.2-11B-Vision-Instruct` | `cstar` | New VLM |
| `qwen3-vl-8b-thinking` | `Qwen/Qwen3-VL-8B-Thinking` | `cstar` | New VLM |
| `internvl-3.5-8b` | `OpenGVLab/InternVL3_5-8B` | `cstar` | New VLM |
| `qwen3-vl-32b-fp8` | `Qwen/Qwen3-VL-32B-Instruct-FP8` | `cstar` | New VLM / FP8 |

## Server Roles

### spectre

```text
host: long-horizon@10.4.25.44
GPU: RTX 6000 Ada, 48 GB VRAM
observed CUDA/driver behavior: CUDA 12.4-compatible stack is required
best role: AWQ LLM serving, especially DeepSeek-32B and Llama-70B AWQ
avoid: CUDA 13 PyTorch builds
```

Use `spectre` for the AWQ text LLMs. Its 48 GB VRAM is much friendlier than the 5090 for larger quantized language models.

### cstar

```text
host: long-horizon@10.10.16.68
GPU: RTX 5090, 32 GB VRAM
observed driver/CUDA: driver 580.95.05, CUDA 13.0
best role: newer VLMs, source Transformers, FP8 experiments
watch-out: 32 GB VRAM is tight for 27B/32B/38B models unless quantized
```

Use `cstar` for Qwen3-VL, InternVL, Llama Vision, and FP8 models.

## Sync Code To Servers

Use a dated folder so each server copy is explicit:

```bash
ssh long-horizon@10.4.25.44 "mkdir -p ~/TAMP-PDDL-2026-06-04"
ssh long-horizon@10.10.16.68 "mkdir -p ~/TAMP-PDDL-2026-06-04"
```

Sync useful code only:

```bash
rsync -avz --delete \
  --exclude ".git" \
  --exclude ".venv*" \
  --exclude "__pycache__" \
  --exclude ".pytest_cache" \
  --exclude "eval_results_10_trials" \
  --exclude "llm_pipeline/results" \
  llm_pipeline vlm_pipeline evaluation run_10_trials_and_aggregate.py MODEL_SERVER_REQUIREMENTS.md \
  long-horizon@10.4.25.44:~/TAMP-PDDL-2026-06-04/
```

For `cstar`, change the destination:

```bash
rsync -avz --delete \
  --exclude ".git" \
  --exclude ".venv*" \
  --exclude "__pycache__" \
  --exclude ".pytest_cache" \
  --exclude "eval_results_10_trials" \
  --exclude "llm_pipeline/results" \
  llm_pipeline vlm_pipeline evaluation run_10_trials_and_aggregate.py MODEL_SERVER_REQUIREMENTS.md \
  long-horizon@10.10.16.68:~/TAMP-PDDL-2026-06-04/
```

## Environment 1: Standard LLM Env

Use for:

```text
deepseek-r1-qwen-14b
qwen3-8b
```

On either server:

```bash
cd ~/TAMP-PDDL-2026-06-04
uv venv .venv_llm
source .venv_llm/bin/activate
uv pip install -U pip
uv pip install fastapi uvicorn pydantic accelerate transformers safetensors sentencepiece protobuf huggingface_hub requests bitsandbytes
```

On `spectre`, force CUDA 12.4 PyTorch:

```bash
uv pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
```

On `cstar`, CUDA 13-era wheels/source stack is acceptable:

```fish
uv pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu130
```

Start DeepSeek-14B:

```bash
python -m llm_pipeline.server \
  --model deepseek-r1-qwen-14b \
  --host 0.0.0.0 \
  --port 8000 \
  --device cuda
```

Start Qwen3-8B:

```bash
python -m llm_pipeline.server \
  --model qwen3-8b \
  --host 0.0.0.0 \
  --port 8000 \
  --device cuda
```

## Environment 2: AWQ LLM Env On spectre

Use for:

```text
deepseek-r1-qwen-32b
llama-3.3-70b-awq
```

Setup:

```bash
cd ~/TAMP-PDDL-2026-06-04
uv venv .venv_awq
source .venv_awq/bin/activate
uv pip install -U pip
uv pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
uv pip install fastapi uvicorn pydantic accelerate safetensors sentencepiece protobuf huggingface_hub requests
uv pip install "transformers==4.51.3"
uv pip install "autoawq==0.2.9" --no-deps
uv pip uninstall torchao llmcompressor compressed-tensors autoawq-kernels
```

Sanity check:

```bash
python -c "import torch; print(torch.__version__); print(torch.version.cuda); print(torch.cuda.is_available())"
python -c "from transformers import Qwen2ForCausalLM; print('qwen2 ok')"
```

Start DeepSeek-32B AWQ from the local cache:

```bash
CUDA_VISIBLE_DEVICES=1 python -m llm_pipeline.server \
  --model /scratch4/long-horizon/hub/models--casperhansen--deepseek-r1-distill-qwen-32b-awq/snapshots/e20a4933e66aa5eccc8270489f5aeab17f90b888 \
  --host 127.0.0.1 \
  --port 8020 \
  --device cuda \
  --no-4bit
```

Start Llama-70B AWQ:

```bash
CUDA_VISIBLE_DEVICES=1 python -m llm_pipeline.server \
  --model llama-3.3-70b-awq \
  --host 127.0.0.1 \
  --port 8020 \
  --device cuda \
  --no-4bit
```

Important:

```text
AWQ checkpoints are already quantized. Always use --no-4bit.
Do not install source/nightly Transformers into .venv_awq.
Do not install torch cu130 on spectre.
```

## Environment 3: New VLM / FP8 Env On cstar

Use for:

```text
qwen3-vl-8b-thinking
qwen3-vl-32b-fp8
qwen2.5-vl-72b-awq
internvl-3.5-8b
internvl-3.5-38b
llama-3.2-11b-vision
qwen3.6-27b FP8/source-Transformers experiments
```

Fish shell setup:

```fish
cd ~/TAMP-PDDL-2026-06-04
uv venv .venv_vlm --python 3.13
source .venv_vlm/bin/activate.fish
uv pip install -U pip
uv pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu130
uv pip install accelerate fastapi uvicorn pydantic requests pillow qwen-vl-utils safetensors sentencepiece protobuf huggingface_hub bitsandbytes
uv pip install git+https://github.com/huggingface/transformers.git
```

Sanity checks:

```fish
python -c "import torch; print(torch.__version__); print(torch.version.cuda); print(torch.cuda.is_available())"
python -c "import transformers; print(transformers.__version__); from transformers import AutoConfig; print('transformers ok')"
```

Start Qwen3-VL 8B:

```fish
python -m llm_pipeline.server \
  --model qwen3-vl-8b-thinking \
  --model-type vlm \
  --host 0.0.0.0 \
  --port 8000 \
  --device cuda \
  --no-4bit
```

Start Qwen3-VL 32B FP8:

```fish
python -m llm_pipeline.server \
  --model qwen3-vl-32b-fp8 \
  --model-type vlm \
  --host 0.0.0.0 \
  --port 8000 \
  --device cuda \
  --no-4bit
```

Start InternVL 8B:

```fish
python -m llm_pipeline.server \
  --model internvl-3.5-8b \
  --model-type vlm \
  --host 0.0.0.0 \
  --port 8000 \
  --device cuda \
  --no-4bit
```

Start InternVL 38B:

```fish
python -m llm_pipeline.server \
  --model internvl-3.5-38b \
  --model-type vlm \
  --host 0.0.0.0 \
  --port 8000 \
  --device cuda \
  --no-4bit
```

Start Llama Vision:

```fish
python -m llm_pipeline.server \
  --model llama-3.2-11b-vision \
  --model-type vlm \
  --host 0.0.0.0 \
  --port 8000 \
  --device cuda \
  --no-4bit
```

Start Qwen3.6-27B FP8 snapshot:

```fish
python -m llm_pipeline.server \
  --model /path/to/qwen3.6-27b-fp8-snapshot \
  --model-type llm \
  --host 0.0.0.0 \
  --port 8000 \
  --device cuda \
  --no-4bit
```

If a 27B/32B/38B model logs CPU offload and then CPU hits 100%, stop using that exact load configuration for batches. It is too slow or not fitting cleanly.

## Port Forwarding

From your local machine:

```bash
ssh -L 8000:127.0.0.1:8000 long-horizon@10.10.16.68
```

For `spectre` on port `8020`:

```bash
ssh -L 8020:127.0.0.1:8020 long-horizon@10.4.25.44
```

Then local trial commands use:

```bash
--remote-url http://127.0.0.1:8000
```

or:

```bash
--remote-url http://127.0.0.1:8020
```

## Smoke Test Before Batch

Always run one trial first:

```bash
python -m llm_pipeline.trial_runner \
  --variant K1 \
  --model MODEL_ALIAS \
  --icl-mode zero_shot \
  --trial-index 1 \
  --remote \
  --remote-url http://127.0.0.1:8000 \
  --planner-max-new-tokens 768 \
  --goal-check-max-new-tokens 64 \
  --max-replans 2 \
  --headless
```

For bigger reasoning models, use a tighter token cap:

```bash
--planner-max-new-tokens 512
```

Run the full batch only after the smoke test returns normally:

```bash
python run_10_trials_and_aggregate.py \
  --model MODEL_ALIAS \
  --variant K1 \
  --trials 10 \
  --icl-mode zero_shot \
  --remote \
  --remote-url http://127.0.0.1:8000 \
  --planner-max-new-tokens 768 \
  --goal-check-max-new-tokens 64
```

For VLMs:

```bash
python run_10_trials_and_aggregate.py \
  --pipeline vlm \
  --model MODEL_ALIAS \
  --model-type vlm \
  --variant K1 \
  --trials 10 \
  --icl-mode zero_shot \
  --remote \
  --remote-url http://127.0.0.1:8000 \
  --planner-max-new-tokens 768 \
  --goal-check-max-new-tokens 64
```

## Health Checks

Server:

```bash
curl --max-time 90 http://127.0.0.1:8000/health
```

GPU:

```bash
nvidia-smi
nvidia-smi pmon -c 5
```

CPU/RAM:

```bash
top -u long-horizon
free -h
ps -u long-horizon -o pid,etime,%cpu,%mem,cmd --sort=-%cpu | head -20
```

PyTorch:

```bash
python -c "import torch; print(torch.__version__); print(torch.version.cuda); print(torch.cuda.is_available())"
```

## Error Map

### `NVIDIA driver on your system is too old ... found version 12040`

You installed a CUDA 13 PyTorch build on `spectre`. Reinstall cu124 PyTorch.

```bash
uv pip uninstall torch torchvision torchaudio
uv pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
```

### `AwqConfig but you are passing a BitsAndBytesConfig`

You loaded an AWQ checkpoint with BitsAndBytes 4-bit. Use:

```bash
--no-4bit
```

### `module 'torch.utils._pytree' has no attribute 'register_constant'`

`torchao` is incompatible with the pinned AWQ env. Remove it:

```bash
uv pip uninstall torchao
```

### `model type qwen3_vl/qwen3_5 not recognized`

Transformers is too old. Use the cstar `.venv_vlm` source-Transformers env:

```fish
uv pip install git+https://github.com/huggingface/transformers.git
```

### CPU 100%, GPU partial usage, no output

The model is probably CPU-offloading or generating too many tokens. Fix by:

```text
1. Prefer FP8/AWQ/quantized checkpoint.
2. Use --planner-max-new-tokens 512 or 768.
3. Do not batch until one smoke trial returns.
4. If CPU offload is logged, do not trust that setup for batch tests.
```

### `/health` times out while generation is running

The server is busy inside `model.generate()`. This server is not streaming and does not return partial output. Reduce generation tokens or use a model/load configuration that fits fully on GPU.
