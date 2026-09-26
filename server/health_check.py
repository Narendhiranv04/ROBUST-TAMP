"""Health checks for the ROBUST TAMP vLLM server (127.0.0.1:8000). Stdlib + Pillow only.

Sampling follows the Qwen3-VL-8B-Thinking model card ("Generation Hyperparameters"):
VL: temperature 1.0, top_p 0.95, top_k 20, repetition_penalty 1.0, presence_penalty 0.0;
text: the same with presence_penalty 1.5. min_p is not specified (vLLM default 0.0).
"""
import base64, io, json, subprocess, threading, time, urllib.request
from concurrent.futures import ThreadPoolExecutor

BASE = "http://127.0.0.1:8000"
MODEL = "qwen3-vl-8b-thinking"
VL = dict(temperature=1.0, top_p=0.95, top_k=20, repetition_penalty=1.0, presence_penalty=0.0)
TEXT = dict(VL, presence_penalty=1.5)
MAX_TOKENS = 4096
peak = {"mib": 0}
stop = threading.Event()


def gpu_sampler():
    while not stop.is_set():
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True).stdout.split()
        if out:
            peak["mib"] = max(peak["mib"], max(int(x) for x in out))
        time.sleep(0.5)


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        return json.loads(r.read())


def chat(messages, sampling, max_tokens=MAX_TOKENS):
    body = dict(model=MODEL, messages=messages, max_tokens=max_tokens,
                chat_template_kwargs={"enable_thinking": True}, **sampling)
    req = urllib.request.Request(BASE + "/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=900) as r:
        data = json.loads(r.read())
    dt = time.time() - t0
    ch = data["choices"][0]
    msg = ch["message"]
    reasoning = msg.get("reasoning_content") or msg.get("reasoning") or ""
    toks = data["usage"]["completion_tokens"]
    return dict(latency_s=round(dt, 2), finish_reason=ch["finish_reason"], prompt_tokens=data["usage"]["prompt_tokens"],
                completion_tokens=toks, tokens_per_s=round(toks / dt, 1), reasoning_chars=len(reasoning),
                content=(msg.get("content") or "").strip())


def test_image_b64():
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (448, 336), "white")
    d = ImageDraw.Draw(img)
    d.rectangle([40, 60, 170, 190], fill=(220, 30, 30))       # red square, left
    d.ellipse([260, 80, 390, 210], fill=(30, 60, 220))        # blue circle, right
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def main():
    threading.Thread(target=gpu_sampler, daemon=True).start()
    out = {}
    out["models"] = [m["id"] for m in get("/v1/models")["data"]]
    out["version"] = get("/version")
    out["text"] = chat([{"role": "user", "content": "In one sentence: what does a robot need to check before placing a mug inside a box?"}], TEXT)
    image_msg = [{"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": "data:image/png;base64," + test_image_b64()}},
        {"type": "text", "text": "Name each shape in the image, its colour, and whether it is on the left or the right."}]}]
    out["image"] = chat(image_msg, VL)
    prompts = [f"List {n} kitchen objects a robot could pick up, one per line." for n in (3, 4, 5, 6)]
    t0 = time.time()
    with ThreadPoolExecutor(4) as ex:
        results = list(ex.map(lambda p: chat([{"role": "user", "content": p}], TEXT, max_tokens=1024), prompts))
    wall = time.time() - t0
    out["concurrent4"] = dict(wall_s=round(wall, 2), sum_latency_s=round(sum(r["latency_s"] for r in results), 2),
                              aggregate_tokens_per_s=round(sum(r["completion_tokens"] for r in results) / wall, 1),
                              per_request=[{k: r[k] for k in ("latency_s", "finish_reason", "completion_tokens", "tokens_per_s")}
                                           for r in results])
    stop.set()
    time.sleep(0.6)
    out["peak_gpu_memory_mib"] = peak["mib"]
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
