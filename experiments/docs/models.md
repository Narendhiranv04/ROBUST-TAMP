# Models, downloads and GPU inference

The simulation client and GPU server use separate environments. Only the GPU process downloads weights. No weights, cache, credentials or inference environment are included. All aliases, checkpoint revisions, model types, reasoning modes, sampling presets, special system prompts and vLLM arguments are defined in [`model_profiles.py`](../../src/llm_pipeline/model_profiles.py).

## GPU server

These commands preserve the recorded serving stack; they have **not** been executed on a GPU during release preparation. The selected BF16 8B configuration was recorded on one RTX 5090 with 32 GB memory, driver 580.95.05/CUDA 13.0. The scale study used FP8 checkpoints on an RTX PRO 5000 with 48 GB. This is recorded hardware, not a guarantee that every profile fits every GPU. No new memory estimates are asserted.

Run from the release root on your configured GPU server:

```sh
nvidia-smi
python3.12 -m venv .venv-inference
. .venv-inference/bin/activate
python -m pip install -r requirements-inference.txt -e .
export HF_HOME="$HOME/.cache/robust-tamp-models"
python -m robust_tamp download --model qwen3-vl-8b-thinking
python -m robust_tamp serve --model qwen3-vl-8b-thinking
```

Check occupancy before starting and leave existing jobs alone. `serve` runs in the foreground and does not stop other servers. The default is one GPU, localhost port 8000, context 32,768, memory utilization 0.90, BF16 activation dtype, Qwen3 reasoning parser and at most two images per request. The planner sends one composite image. Output is capped by the client at 24,576 tokens. `--tensor-parallel-size` is explicit; a larger model may need more memory or multiple GPUs.

`download` uses the ordinary `hf download` CLI with the pinned revision. `serve` also calls `snapshot_download` if necessary and serves the resulting **snapshot directory**. This matters: the client verifies the revision from `/v1/models`'s `root` on every call. Serving a bare model identifier can leave that revision unverifiable. The model card's per-profile parser/template arguments are passed unchanged. FP8 profiles retain checkpoint quantization; `--dtype bfloat16` describes activation dtype and does not dequantize their stored weights.

The historical environment recorded vLLM 0.30.0, Torch 2.13.0+cu130, Transformers 5.17.0 and FlashInfer 0.6.18.post1 on Python 3.12.3. CUDA-wheel selection depends on the platform; inspect the installed Torch/CUDA versions before calling it a matched historical environment. FlashInfer warm-up may require a CUDA toolkit and Ninja. See the [official vLLM installation guide](https://docs.vllm.ai/en/stable/getting_started/installation/gpu/) and [serving guide](https://docs.vllm.ai/en/stable/getting_started/quickstart/).

The selected checkpoint is [Qwen/Qwen3-VL-8B-Thinking](https://huggingface.co/Qwen/Qwen3-VL-8B-Thinking), revision `92f3c4b4feadd3a016ef468d103bb5f58b2a2c6b`. Its visual sampling is temperature 1.0, top-p 0.95, top-k 20, min-p 0, repetition penalty 1.0 and presence penalty 0. Thinking is inherent to this checkpoint; the client parses final content separately from reasoning and does not perform hidden format-repair calls.

Use [`hf auth login`](https://huggingface.co/docs/huggingface_hub/en/guides/cli) only when a chosen checkpoint requires account access. Llama profiles may require accepting their access/license terms. Every model has its own model-card license; acceptance and permission to use weights are the downloader's responsibility. The release does not grant weight licenses. Preserve credentials outside the repository.

## Simulation client connection

For a remote GPU, create a tunnel using your own authorized SSH account (separate terminal):

```sh
ssh -N -L 8000:127.0.0.1:8000 USER@GPU_HOST
```

Then, in the simulation environment at the release root:

```sh
python -m robust_tamp doctor --endpoint http://127.0.0.1:8000
python -m robust_tamp run --method full --variants FINAL.G0 --seeds 0 --icl paper --endpoint http://127.0.0.1:8000 --out runs/model-smoke
```

`doctor` checks the server's model list/version; the trial additionally verifies checkpoint revision, reasoning configuration and settings stability. Look for `trial_end` in `runs/model-smoke/FINAL.G0/seed_00/trial_log.jsonl` and use the evaluator report to assess success. A server that answers a health check has not yet passed an end-to-end model trial.

## Historical qualifications

The 0.90 utilization, 32,768 context, parser and image-limit command are recorded for final ICL runs. The zero-shot server command was not saved; matching sampling does not establish identical server configuration. Current client defaults used to have a 900-second request timeout; the release runner explicitly uses the recorded 1,800 seconds. GPU sampling, numerical kernels and concurrent request scheduling prevent a bit-identical-output promise.

Seven planner-comparison conditions lack their final records locally: Qwen3-VL-4B zero-shot; the four 4B/32B ICL rows; and final parser-fix reruns for InternVL3.5-8B and Qwen2.5-7B-Instruct. Older records must not be substituted for those final rows. The profile registry supports launching them, but fresh execution is unverified here.

## Checkpoint registry

The following table is generated from the preserved profile registry. Full 40-character revisions and all sampling/template settings are printed by `python -m robust_tamp profiles`. Hardware fit is only established by the recorded configurations above.

| Profile | Official checkpoint | Revision | Input | Reasoning | Weights |
|---|---|---|---|---|---|
| `qwen3-vl-8b-thinking` | [Qwen/Qwen3-VL-8B-Thinking](https://huggingface.co/Qwen/Qwen3-VL-8B-Thinking) | `92f3c4b4fead` | VLM | on | BF16 |
| `qwen3-vl-4b-thinking` | [Qwen/Qwen3-VL-4B-Thinking](https://huggingface.co/Qwen/Qwen3-VL-4B-Thinking) | `1de27d8c51f1` | VLM | on | BF16 |
| `holo2-8b` | [Hcompany/Holo2-8B](https://huggingface.co/Hcompany/Holo2-8B) | `09cd3b45966f` | VLM | on | BF16 |
| `ministral-3-8b-reasoning` | [mistralai/Ministral-3-8B-Reasoning-2512](https://huggingface.co/mistralai/Ministral-3-8B-Reasoning-2512) | `81eaece1948f` | VLM | on | BF16 |
| `qwen3-vl-8b-instruct` | [Qwen/Qwen3-VL-8B-Instruct](https://huggingface.co/Qwen/Qwen3-VL-8B-Instruct) | `0c351dd01ed8` | VLM | off | BF16 |
| `ministral-3-8b-instruct` | [mistralai/Ministral-3-8B-Instruct-2512-BF16](https://huggingface.co/mistralai/Ministral-3-8B-Instruct-2512-BF16) | `f6fae9795746` | VLM | off | BF16 |
| `internvl3.5-8b` | [OpenGVLab/InternVL3_5-8B](https://huggingface.co/OpenGVLab/InternVL3_5-8B) | `9bb6a56ad9cc` | VLM | off | BF16 |
| `qwen3-8b` | [Qwen/Qwen3-8B](https://huggingface.co/Qwen/Qwen3-8B) | `b968826d9c46` | LLM | on | BF16 |
| `qwen3-4b` | [Qwen/Qwen3-4B](https://huggingface.co/Qwen/Qwen3-4B) | `1cfa9a720891` | LLM | on | BF16 |
| `r1-distill-llama-8b` | [deepseek-ai/DeepSeek-R1-Distill-Llama-8B](https://huggingface.co/deepseek-ai/DeepSeek-R1-Distill-Llama-8B) | `6a6f4aa41979` | LLM | on | BF16 |
| `r1-distill-qwen-7b` | [deepseek-ai/DeepSeek-R1-Distill-Qwen-7B](https://huggingface.co/deepseek-ai/DeepSeek-R1-Distill-Qwen-7B) | `916b56a44061` | LLM | on | BF16 |
| `qwen3-8b-nothink` | [Qwen/Qwen3-8B](https://huggingface.co/Qwen/Qwen3-8B) | `b968826d9c46` | LLM | off | BF16 |
| `llama-3.1-8b-instruct` | [meta-llama/Llama-3.1-8B-Instruct](https://huggingface.co/meta-llama/Llama-3.1-8B-Instruct) | `0e9e39f249a1` | LLM | off | BF16 |
| `qwen2.5-7b-instruct` | [Qwen/Qwen2.5-7B-Instruct](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct) | `a09a35458c70` | LLM | off | BF16 |
| `qwen3-vl-4b-thinking-fp8` | [Qwen/Qwen3-VL-4B-Thinking-FP8](https://huggingface.co/Qwen/Qwen3-VL-4B-Thinking-FP8) | `219b8e195ea3` | VLM | on | FP8 |
| `qwen3-4b-fp8` | [Qwen/Qwen3-4B-FP8](https://huggingface.co/Qwen/Qwen3-4B-FP8) | `96b30dc13593` | LLM | on | FP8 |
| `qwen3-vl-8b-thinking-fp8` | [Qwen/Qwen3-VL-8B-Thinking-FP8](https://huggingface.co/Qwen/Qwen3-VL-8B-Thinking-FP8) | `a6638e84662f` | VLM | on | FP8 |
| `qwen3-8b-fp8` | [Qwen/Qwen3-8B-FP8](https://huggingface.co/Qwen/Qwen3-8B-FP8) | `220b46e3b218` | LLM | on | FP8 |
| `qwen3-vl-32b-thinking-fp8` | [Qwen/Qwen3-VL-32B-Thinking-FP8](https://huggingface.co/Qwen/Qwen3-VL-32B-Thinking-FP8) | `3eee143c9b35` | VLM | on | FP8 |
| `qwen3-32b-fp8` | [Qwen/Qwen3-32B-FP8](https://huggingface.co/Qwen/Qwen3-32B-FP8) | `aa55da1ecc13` | LLM | on | FP8 |
