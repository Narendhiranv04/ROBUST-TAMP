# LLM/VLM Server and Evaluation Runbook

This is the short operational guide for syncing the maintained pipeline code, running inference servers, and launching aggregate trials.

## 1. Sync Code to an Inference-Only Server

Run these from the local trial machine, inside the repo root:

```bash
ssh long-horizon@10.4.25.44 "mkdir -p ~/TAMP-PDDL"
```

```bash
rsync -avz \
  --exclude '__pycache__/' \
  --exclude '.pytest_cache/' \
  --exclude '*.pyc' \
  llm_pipeline/ \
  long-horizon@10.4.25.44:~/TAMP-PDDL/llm_pipeline/
```

```bash
rsync -avz \
  --exclude '__pycache__/' \
  --exclude '.pytest_cache/' \
  --exclude '*.pyc' \
  vlm_pipeline/ \
  long-horizon@10.4.25.44:~/TAMP-PDDL/vlm_pipeline/
```

For an inference-only server, `llm_pipeline/` and `vlm_pipeline/` are enough.

Do not sync:

```text
eval_results_10_trials/
RLBench/
pddlstream/
task1_variation*.ttt
rlbench_kitchen_env.py
rlbench_kitchen_streams.py
```

Those are for the simulator/trial machine, not the inference server.

## 2. Set Up the Server Environment

SSH into the server:

```bash
ssh long-horizon@10.4.25.44
```

Go to the server folder:

```bash
cd ~/TAMP-PDDL
```

Create and activate the virtual environment:

```bash
uv venv
```

```bash
source .venv/bin/activate
```

Install server dependencies:

```bash
uv pip install fastapi uvicorn pydantic transformers accelerate safetensors sentencepiece protobuf huggingface_hub bitsandbytes
```

Install PyTorch compatible with the RTX 6000 Ada server driver/CUDA 12.4:

```bash
uv pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
```

Check CUDA:

```bash
python -c "import torch; print(torch.__version__); print(torch.version.cuda); print(torch.cuda.is_available())"
```

You want:

```text
torch.cuda.is_available() = True
```

For AWQ models, install the compatible AWQ stack:

```bash
uv pip install "transformers==4.51.3" accelerate safetensors sentencepiece protobuf
```

```bash
uv pip install "autoawq==0.2.9" --no-deps
```

If `torchao`, `llmcompressor`, `compressed-tensors`, or `autoawq-kernels` cause import errors, remove them:

```bash
uv pip uninstall torchao llmcompressor compressed-tensors autoawq-kernels
```

AWQ import warnings about deprecation are okay. Tracebacks are not.

## 3. Start an Inference Server

### Official DeepSeek 14B

Use this for the normal `deepseek-r1-qwen-14b` server:

```bash
cd ~/TAMP-PDDL
source .venv/bin/activate
python -m llm_pipeline.server --model deepseek-r1-qwen-14b --host 127.0.0.1 --port 8000
```

This model uses the server's default 4-bit BitsAndBytes loading.

### AWQ DeepSeek 32B

For the downloaded 32B AWQ snapshot:

```bash
cd ~/TAMP-PDDL
source .venv/bin/activate
python -m llm_pipeline.server \
  --model /scratch4/long-horizon/hub/models--casperhansen--deepseek-r1-distill-qwen-32b-awq/snapshots/e20a4933e66aa5eccc8270489f5aeab17f90b888 \
  --host 127.0.0.1 \
  --port 8020 \
  --no-4bit
```

Use `--no-4bit` for AWQ models because they are already quantized. Do not combine AWQ with BitsAndBytes 4-bit.

## 4. Forward Server Ports to the Local Trial Machine

If the server is listening on remote port `8000`:

```bash
ssh -L 8000:127.0.0.1:8000 long-horizon@10.4.25.44
```

If local `8000` is already occupied, forward remote `8000` to local `8001`:

```bash
ssh -L 8001:127.0.0.1:8000 long-horizon@10.4.25.44
```

If the 32B server is listening on remote port `8020`:

```bash
ssh -L 8020:127.0.0.1:8020 long-horizon@10.4.25.44
```

Test a forwarded server from the local machine:

```bash
curl http://127.0.0.1:8000/health
```

or:

```bash
curl http://127.0.0.1:8020/health
```

The health response should show:

```json
"model_loaded": true
```

## 5. Check and Kill Server Processes

Show GPU usage:

```bash
nvidia-smi
```

Inspect a process:

```bash
ps -fp PID_HERE
```

Find your LLM server:

```bash
ps -u long-horizon -o pid,etime,%cpu,%mem,cmd | grep llm_pipeline.server
```

Stop your server gently:

```bash
kill PID_HERE
```

Force stop only if needed:

```bash
kill -9 PID_HERE
```

Only kill processes you own or are sure you started.

## 6. Set Up the Local Trial Machine

From the local repo root:

```bash
cd /home/boreddog/Documents/RRC/Long_Horizon/Ending_Pipeline
```

Activate your existing simulator environment:

```bash
source activate_gt_env.sh
```

If you use a conda environment instead, activate that environment before running trials:

```bash
conda activate TAMP-PDDL
```

Check that the LLM pipeline imports:

```bash
python -m llm_pipeline.trial_runner --help
```

Check the aggregate runner:

```bash
python run_10_trials_and_aggregate.py --help
```

## 7. Run One Trial

Example: rerun K3 `trial_006` and save into the existing result folder:

```bash
python -m llm_pipeline.trial_runner \
  --variant K3 \
  --model deepseek-r1-qwen-14b \
  --icl-mode zero_shot \
  --trial-index 6 \
  --remote \
  --remote-url http://127.0.0.1:8000 \
  --headless \
  --max-replans 10 \
  --output-dir eval_results_10_trials/deepseek-r1-qwen-14b/K3/trial_006
```

If the simulator gives a Qt platform error, retry with:

```bash
QT_QPA_PLATFORM=offscreen python -m llm_pipeline.trial_runner \
  --variant K3 \
  --model deepseek-r1-qwen-14b \
  --icl-mode zero_shot \
  --trial-index 6 \
  --remote \
  --remote-url http://127.0.0.1:8000 \
  --headless \
  --max-replans 10 \
  --output-dir eval_results_10_trials/deepseek-r1-qwen-14b/K3/trial_006
```

## 8. Run Aggregate Tests

Run 10 headless trials for one variant:

```bash
python run_10_trials_and_aggregate.py \
  --pipeline llm \
  --model deepseek-r1-qwen-14b \
  --variant K3 \
  --trials 10 \
  --icl-mode zero_shot \
  --remote \
  --remote-url http://127.0.0.1:8000 \
  --headless \
  --max-replans 10
```

Run only 5 trials:

```bash
python run_10_trials_and_aggregate.py \
  --pipeline llm \
  --model deepseek-r1-qwen-14b \
  --variant K1 \
  --trials 5 \
  --icl-mode zero_shot \
  --remote \
  --remote-url http://127.0.0.1:8000 \
  --headless \
  --max-replans 10
```

Aggregate existing records without running new trials:

```bash
python run_10_trials_and_aggregate.py \
  --pipeline llm \
  --model deepseek-r1-qwen-14b \
  --variant K3 \
  --trials 10 \
  --icl-mode zero_shot \
  --remote \
  --remote-url http://127.0.0.1:8000 \
  --headless \
  --max-replans 10 \
  --aggregate-only
```

Use the 32B server by changing only the model name and remote URL:

```bash
python run_10_trials_and_aggregate.py \
  --pipeline llm \
  --model deepseek-r1-qwen-32b \
  --variant K3 \
  --trials 10 \
  --icl-mode zero_shot \
  --remote \
  --remote-url http://127.0.0.1:8020 \
  --headless \
  --max-replans 10
```

## 9. Result Locations

Repeated-trial results are written under:

```text
eval_results_10_trials/<model>/<variant>/trial_XXX/
```

Each trial folder should contain:

```text
record.json
failure_summary.txt
```

The aggregate file is:

```text
eval_results_10_trials/<model>/<variant>/aggregate_summary.json
```

## 10. K3 Metric Reminder

K3 has 7 expected subtasks:

```text
mug_to_placement:     1
open_lid:             1
grocery_to_cupboard:  2
mug_to_box:           3
```

Total:

```text
1 + 1 + 2 + 3 = 7
```

`Mean Raw Task Success` is the simulator's raw success signal.

`Mean Task Success` is the stricter benchmark success after subtask and goal-check scoring.
