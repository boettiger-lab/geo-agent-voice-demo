#!/usr/bin/env python3
"""
Probe a vLLM-backed Gemma 4 chat completions endpoint with several
candidate audio-content schemas, to determine which payload shape the
serving stack parses and whether the deployed model can actually
transcribe audio end-to-end.

Configurable via env vars (with defaults targeting NRP's audio-capable
gemma variant):
    ENDPOINT  default: https://ellm.nrp-nautilus.io/v1/chat/completions
    MODEL     default: gemma-4-e4b
    NRP_TOKEN required: bearer token for the configured endpoint

================================================================
TEST HISTORY
================================================================

**2026-04-08 — NRP `gemma` (= google/gemma-4-31B-it)**
  Schema A returns HTTP 400 with the model-aware error:
    "Audio input was provided but the model 'google/gemma-4-31B-it' does
     not have an audio tower. Audio inference is only supported for
     Gemma4 models that include an audio_config."
  → Wire format confirmed correct; 31B variant has no audio tower (matches
    HF blog: only the E-series Gemma 4 builds ship `audio_config`).
  Schemas B–E (HF `type: audio` + url, `audio_url`, data: URIs, etc.) all
  return "malformed request: failed to parse JSON" — settled as
  non-functional against the vLLM serving stack; don't bother re-probing.

**2026-04-09 — NRP `gemma-4-e4b` (= google/gemma-4-E4B-it)**
  NRP added an audio-tower variant. Schema A returns HTTP 500 with:
    "Please install vllm[audio] for audio support"
  → Right model (audio tower present) but the NRP vLLM image is missing
    the `vllm[audio]` extras (`librosa`, `soundfile`, etc.). Server-side
    install fix; no client changes needed. Re-run when NRP redeploys.

**2026-04-09 — Nimbus `gemma4` (= google/gemma-4-E2B-it)**
  Endpoint: https://gemma4-nimbus.carlboettiger.info/v1/chat/completions
  Schema A returns HTTP 200 with a clean transcription of sample.mp3
  ("This week I traveled to Chicago to deliver my final farewell address
  to the nation..."). 771 prompt tokens / 93 completion tokens for ~45s
  of audio.
  → End-to-end voice path verified. The recipe (`vllm[audio]` installed
    on top of an audio-tower Gemma 4 build) works. The geo-agent
    voice-input-explore branch needs no code changes — it has been
    sending the right wire format all along.

================================================================
CONCLUSIONS
================================================================

1. **Wire format**: OpenAI `input_audio` (schema A) is the only shape any
   vLLM-backed Gemma 4 deployment will accept. All other shapes fail at
   JSON parsing. Settled — do not re-test B–E.

2. **Model variant**: only Gemma 4 builds with `audio_config` (E2B and
   E4B per HF) can do audio. NRP's `gemma` 31B cannot.

3. **Server install**: `vllm[audio]` extras must be installed alongside
   the audio-capable model. Without them you get a 500 even with the
   right model and right wire format.

4. **Routing**: the geo-agent webapp must reach an audio-capable endpoint
   through a CORS-fronting proxy (the browser can't hit
   `gemma4-nimbus.carlboettiger.info` directly). See open-llm-proxy#9 for
   the proxy provider entry that adds `gemma4` routing.
"""
import base64
import json
import os
import sys
import urllib.request
import urllib.error

ENDPOINT = os.environ.get("ENDPOINT", "https://ellm.nrp-nautilus.io/v1/chat/completions")
MODEL = os.environ.get("MODEL", "gemma-4-e4b")
PUBLIC_MP3 = "https://huggingface.co/datasets/hf-internal-testing/dummy-audio-samples/resolve/main/obama_first_45_secs.mp3"

token = os.environ.get("NRP_TOKEN")
if not token:
    sys.exit("NRP_TOKEN not set")

print(f"endpoint: {ENDPOINT}")
print(f"model:    {MODEL}")
print()

with open(os.path.join(os.path.dirname(__file__), "sample.mp3"), "rb") as f:
    b64 = base64.b64encode(f.read()).decode()

text_prompt = "Please transcribe this audio as accurately as you can."

probes = {
    "A_openai_input_audio_b64": {
        "content": [
            {"type": "text", "text": text_prompt},
            {"type": "input_audio", "input_audio": {"data": b64, "format": "mp3"}},
        ],
    },
    "B_hf_audio_url_public": {
        "content": [
            {"type": "text", "text": text_prompt},
            {"type": "audio", "url": PUBLIC_MP3},
        ],
    },
    "C_audio_url_data_uri": {
        "content": [
            {"type": "text", "text": text_prompt},
            {"type": "audio_url", "audio_url": {"url": f"data:audio/mp3;base64,{b64}"}},
        ],
    },
    "D_audio_url_public": {
        "content": [
            {"type": "text", "text": text_prompt},
            {"type": "audio_url", "audio_url": {"url": PUBLIC_MP3}},
        ],
    },
    "E_hf_audio_data_uri": {
        "content": [
            {"type": "text", "text": text_prompt},
            {"type": "audio", "url": f"data:audio/mp3;base64,{b64}"},
        ],
    },
}

def call(name, content):
    payload = {
        "model": MODEL,
        "max_tokens": 300,
        "messages": [{"role": "user", "content": content}],
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        ENDPOINT,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    print("=" * 70)
    print("PROBE:", name)
    print("=" * 70)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = resp.read().decode()
            print("HTTP", resp.status)
            try:
                j = json.loads(body)
                msg = j.get("choices", [{}])[0].get("message", {})
                print("content:", (msg.get("content") or "")[:1000])
                print("usage:", j.get("usage"))
            except Exception:
                print(body[:1500])
    except urllib.error.HTTPError as e:
        print("HTTP", e.code)
        try:
            print(e.read().decode()[:1500])
        except Exception:
            print(str(e))
    except Exception as e:
        print("ERR", type(e).__name__, str(e)[:500])
    print()

for name, spec in probes.items():
    call(name, spec["content"])
