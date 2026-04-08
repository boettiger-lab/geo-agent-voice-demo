#!/usr/bin/env python3
"""
Probe the NRP ellm gemma endpoint with several audio-content schemas.

Conclusion from 2026-04-08 run against `gemma` (= google/gemma-4-31B-it):
  * Schema A  (OpenAI `input_audio` with base64 data + format) is the ONLY
    payload shape the serving stack parses. It returns HTTP 400 with:
      "Audio input was provided but the model 'google/gemma-4-31B-it' does
       not have an audio tower. Audio inference is only supported for
       Gemma4 models that include an audio_config."
    → wire format confirmed; the 31B variant NRP deploys has no audio tower.
  * Schemas B–E (HF `type: audio` + url, `audio_url`, data: URIs, etc.)
    all return "malformed request: failed to parse JSON" — unrelated to
    the model, the serving stack just doesn't recognize those shapes.

Re-run this after NRP deploys a Gemma 4 E2B/E4B (or any audio_config build):
if schema A starts returning a 200 with a transcript, the geo-agent
voice-input-explore branch should work end-to-end without any code change.

Requires: NRP_TOKEN in env, sample.mp3 next to this script.
"""
import base64
import json
import os
import sys
import urllib.request
import urllib.error

ENDPOINT = "https://ellm.nrp-nautilus.io/v1/chat/completions"
PUBLIC_MP3 = "https://huggingface.co/datasets/hf-internal-testing/dummy-audio-samples/resolve/main/obama_first_45_secs.mp3"

token = os.environ.get("NRP_TOKEN")
if not token:
    sys.exit("NRP_TOKEN not set")

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
        "model": "gemma",
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
