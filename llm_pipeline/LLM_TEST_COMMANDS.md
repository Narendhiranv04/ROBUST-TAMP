# LLM Trial Runner Commands

This runbook covers how to test different LLMs with the maintained `llm_pipeline`
trial runner, either through the local planner server or by loading the model
directly inside the trial process.

## Setup

```sh
cd /home/naren/iiith/TAMP-PDDL-11-Feb/TAMP-PDDL
source .venv/bin/activate
```

List registered LLM aliases:

```sh
python -m llm_pipeline.server --list-models
```

Common aliases in this workspace:

```txt
qwen
deepseek-r1
deepseek-r1-llama-8b
deepseek-r1-qwen-14b
mistral-nemo
selene
```

## Server Mode

Use this for most testing. The server keeps the model loaded, and the trial
runner calls it through HTTP.

### Terminal 1: Start The LLM Server

```sh
python -m llm_pipeline.server \
  --host 0.0.0.0 \
  --port 8000 \
  --model qwen \
  --device cuda
```

The server uses 4-bit quantization by default. To disable 4-bit:

```sh
python -m llm_pipeline.server \
  --host 0.0.0.0 \
  --port 8000 \
  --model qwen \
  --device cuda \
  --no-4bit
```

### Terminal 2: Run One Trial

```sh
python -m llm_pipeline.trial_runner \
  --variant G1 \
  --model qwen \
  --icl-mode zero_shot \
  --remote \
  --remote-url http://127.0.0.1:8000 \
  --gui \
  --max-replans 1
```

Run with a custom goal:

```sh
python -m llm_pipeline.trial_runner \
  --variant G1 \
  --model qwen \
  --icl-mode zero_shot \
  --remote \
  --remote-url http://127.0.0.1:8000 \
  --gui \
  --max-replans 1 \
  --goal "Cook the meat using the grill, serve the cooked meat on the plate in the serving area, and keep the spam on the table."
```

## Local Lightweight Test

For weaker local machines, use a smaller Hugging Face model path through the
server. This keeps quantization available while avoiding the larger registered
models.

### Terminal 1: Start Small Local Model

Fastest smoke test:

```sh
python -m llm_pipeline.server \
  --host 127.0.0.1 \
  --port 8000 \
  --model Qwen/Qwen2.5-0.5B-Instruct \
  --device cuda
```

Slightly stronger, but heavier:

```sh
python -m llm_pipeline.server \
  --host 127.0.0.1 \
  --port 8000 \
  --model Qwen/Qwen2.5-1.5B-Instruct \
  --device cuda
```

### Terminal 2: Run Trial Against Small Model

```sh
python -m llm_pipeline.trial_runner \
  --variant G1 \
  --model Qwen/Qwen2.5-0.5B-Instruct \
  --icl-mode zero_shot \
  --remote \
  --remote-url http://127.0.0.1:8000 \
  --gui \
  --max-replans 1
```

## Direct Local Mode

This loads the model inside the trial process. Use only for tiny models because
there is no trial-runner CLI flag for 4-bit quantization in this mode.

```sh
python -m llm_pipeline.trial_runner \
  --variant G1 \
  --model Qwen/Qwen2.5-0.5B-Instruct \
  --icl-mode zero_shot \
  --gui \
  --max-replans 1
```

## Batch Testing

Run all grill variants against the currently running server:

```sh
for variant in G1 G2 G3; do
  python -m llm_pipeline.trial_runner \
    --variant "$variant" \
    --model qwen \
    --icl-mode zero_shot \
    --remote \
    --remote-url http://127.0.0.1:8000 \
    --headless \
    --max-replans 1
done
```

Run both prompt modes for one variant:

```sh
for icl in zero_shot few_shot_shared_1; do
  python -m llm_pipeline.trial_runner \
    --variant G1 \
    --model qwen \
    --icl-mode "$icl" \
    --remote \
    --remote-url http://127.0.0.1:8000 \
    --headless \
    --max-replans 1
done
```

To compare different LLMs, restart the server with a new `--model`, then rerun
the same trial command.

## Outputs

By default, outputs are saved under:

```txt
llm_pipeline/results/llm_runs/<timestamp>_<variant>_<model>_<icl>_trial_XXX/
```

Each run writes:

```txt
record.json
failure_summary.txt
```

Use `--output-dir` to force a specific run folder:

```sh
python -m llm_pipeline.trial_runner \
  --variant G1 \
  --model qwen \
  --icl-mode zero_shot \
  --remote \
  --remote-url http://127.0.0.1:8000 \
  --gui \
  --max-replans 1 \
  --output-dir llm_pipeline/results/llm_runs/manual_G1_qwen_zero_shot
```

