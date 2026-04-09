# geo-agent voice input demo

A minimal demo deployment showing the **optional voice-input layer** for
[geo-agent](https://github.com/boettiger-lab/geo-agent) — see
[geo-agent#131](https://github.com/boettiger-lab/geo-agent/issues/131)
and [geo-agent#136](https://github.com/boettiger-lab/geo-agent/issues/136)
for the two-phase pipeline design.

The 🎤 button next to Send appears whenever `config.transcription_model`
is set (see `k8s/configmap.yaml`). Click it to record, click again to
stop — the audio is sent to the transcription model, the transcript lands
in the input field for review/edit, and pressing Send dispatches the text
through the normal agent loop using whichever model the user has selected.

**Key property:** voice input is decoupled from the active agent model.
You can use MiniMax M2, GLM-4.7, Qwen3, Kimi, GPT-OSS, or Gemma 31B as the
agent — the transcription is always handled by `gemma-4-e4b` (the
audio-capable Gemma 4 E4B variant on NRP).

> This demo is pinned to a SHA of the core library's
> `voice-transcription-split` branch (PR #137), not `@main`. Tests must
> run against this pin *before* the PR merges. Swap to `@main` or a
> tagged release after merge.

## Structure

```
index.html          ← loads core JS/CSS from geo-agent@<sha>
layers-input.json   ← STAC collections + welcome text + model list (for local dev, user-provided mode)
system-prompt.md    ← voice-aware system prompt
k8s/                ← server-side key injection; configmap.yaml sets transcription_model + agent model list
scripts/            ← probe_audio_schemas.py for verifying endpoint/model wire-format compatibility
```

## Local development

```bash
cd geo-agent-voice-demo
python -m http.server 8000
# open http://localhost:8000
```

On first load you'll be prompted for an API key. Point the **Endpoint** at
`https://open-llm-proxy.nrp-nautilus.io/v1` and paste your proxy key. The
🎤 button should appear immediately (no model selection needed —
transcription is decoupled from the agent model).

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

## Verifying the transcription backend

Use the probe script to confirm the configured endpoint/model still
accepts the OpenAI `input_audio` wire format:

```bash
cd scripts
NRP_TOKEN=<your-nrp-token> MODEL=gemma-4-e4b \
  ENDPOINT=https://open-llm-proxy.nrp-nautilus.io/v1/chat/completions \
  python3 probe_audio_schemas.py
```

Probe A (`A_openai_input_audio_b64`) should return HTTP 200 with a
transcription of `sample.mp3`. All other probes are settled failures —
see the test history at the top of `probe_audio_schemas.py` for details.

## Voice path caveats

- Audio is captured by `MediaRecorder` (usually `webm`/`opus`) and
  client-side transcoded to WAV before upload — see the core library's
  `app/voice-input.js`.
- Only the transcription API call carries audio; history stores plain
  text only.
- Browser mic permission is required; the button is a no-op until granted.
- Transcription model training data is speech-only — no music or
  non-speech audio.
- Multi-lingual support is an open question; see geo-agent#136.
