# geo-agent voice input demo

A minimal demo deployment showing the **optional voice-input layer** for
[geo-agent](https://github.com/boettiger-lab/geo-agent) — see
[geo-agent#131](https://github.com/boettiger-lab/geo-agent/issues/131).

When the active model advertises `input_modalities: ["text", "audio"]`, a 🎤
button appears next to the Send button. Click it to start recording, click
again to stop — the captured audio is sent to the LLM as an OpenAI multimodal
`input_audio` content part alongside any typed text.

Among our currently configured open models on the NRP proxy, only **Gemma**
(as configured in `k8s/configmap.yaml`) is flagged audio-capable.

> This demo is pinned to the **`voice-input-explore`** branch of the core
> library, not `@main`. Swap to `@main` or a tagged release in `index.html`
> after the feature merges.

## Structure

```
index.html          ← loads core JS/CSS from geo-agent@voice-input-explore
layers-input.json   ← STAC collections + welcome text + model list (for local dev)
system-prompt.md    ← voice-aware system prompt (normalize transcript artifacts, prefer visual actions)
k8s/                ← server-side key injection; configmap.yaml tags gemma with input_modalities
```

## Local development

```bash
cd geo-agent-voice-demo
python -m http.server 8000
# open http://localhost:8000
```

On first load you'll be prompted for an API key. Point the **Endpoint** at the
NRP LLM proxy (`https://open-llm-proxy.nrp-nautilus.io/v1`) and paste your
proxy key. Select **NRP Gemma (voice)** from the model dropdown — the 🎤
button should appear. (Chrome/Edge/Safari will prompt for microphone
permission on first click.)

## Kubernetes deployment

1. Secret (once per namespace):

   ```bash
   kubectl create secret generic open-llm-proxy-secrets \
     --from-literal=proxy-key=YOUR_PROXY_KEY
   ```

2. Push any edits to the GitHub repo (the init container git-clones `main`).

3. Apply:

   ```bash
   kubectl apply -f k8s/
   kubectl rollout restart deployment/voice-demo
   ```

   Deployed at `https://voice-demo.nrp-nautilus.io` (edit `k8s/ingress.yaml`
   for a different hostname).

## Current status (2026-04-08): blocked on upstream model variant

We probed the NRP `gemma` endpoint directly (see `scripts/probe_audio_schemas.py`)
with five candidate audio-content schemas. Only **one** — OpenAI
`{"type": "input_audio", "input_audio": {"data": <base64>, "format": "mp3"}}`
— was recognised by the serving stack. The response was:

> HTTP 400 — "Audio input was provided but the model
> `google/gemma-4-31B-it` does not have an audio tower. Audio inference is
> only supported for Gemma4 models that include an audio_config."

What this means:

1. The wire format our [voice-input-explore](https://github.com/boettiger-lab/geo-agent/tree/voice-input-explore)
   branch sends is **correct**. No client code change needed.
2. NRP currently deploys the **Gemma 4 31B** variant as `gemma`. Per the
   [HF Gemma 4 blog](https://huggingface.co/blog/gemma4), audio input is
   only in the **E2B (2.3B effective)** and **E4B (4.5B effective)** variants
   — the larger models don't ship an audio tower.
3. **This demo cannot transcribe voice end-to-end until NRP adds a
   Gemma 4 E2B or E4B deployment** (or any build that includes `audio_config`).
   The mic button, capture pipeline, and API payload are all in place and
   waiting.

### Reproducing the probe

```bash
cd scripts
NRP_TOKEN=<your-nrp-ellm-token> python3 probe_audio_schemas.py
```

When an audio-capable gemma variant is deployed, schema A should return
HTTP 200 with a transcript and this demo will start working without any
code changes.

## Other caveats (voice path)

- Audio is sent in whatever container `MediaRecorder` negotiates — usually
  `webm`/`opus`. Gemma's audio tower is documented as accepting mp3, wav
  and similar; a client-side transcode to wav/PCM16 may be needed if the
  negotiated container is rejected.
- Only the current turn carries audio; message history stores a `[voice
  message]` shadow so raw audio doesn't bloat the rolling context window.
- Browser mic permission is required; the button will no-op until granted.
- Training data was speech-only — no music or non-speech audio.
