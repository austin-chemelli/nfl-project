# Desktop LLM setup (Windows)

Setting up the spare desktop as the project's local LLM and search server (ADR 0014). About an hour, mostly downloads. Versions and support facts were checked on 2026-10-28; recheck the two version pins (driver, Ollama) if you do this much later.

**What you end up with:** Ollama serving Qwen3.5-9B and SearXNG serving search results, both reachable only from your own devices over Tailscale. The laptop's pipeline calls them over the network.

## 1. NVIDIA driver (Pascal-safe)

The GTX 1070 is a Pascal card. CUDA 13 dropped Pascal; the 580 driver branch is the last that supports it, and Ollama needs driver 570 or newer for this card.

1. Install the latest **580-branch** Game Ready or Studio driver for the GTX 1070 from NVIDIA.
2. Check in PowerShell: `nvidia-smi` should show the driver version (580.x) and the GTX 1070 with 8 GB.
3. Don't let Windows Update replace it with a newer branch that drops Pascal: if a future branch drops the card, roll back to 580.

## 2. Ollama and the model

1. Install Ollama for Windows from ollama.com. It installs a background service.
2. Set environment variables (System Properties → Environment Variables → System), then restart Ollama from the tray:
   - `OLLAMA_HOST` = `0.0.0.0:11434` (listen on the network; the firewall rule in step 5 limits who can reach it)
   - `OLLAMA_CONTEXT_LENGTH` = `16384`
   - `OLLAMA_FLASH_ATTENTION` = `1`
   - `OLLAMA_KV_CACHE_TYPE` = `q8_0` (halves the context's memory; needs flash attention)
   - `OLLAMA_KEEP_ALIVE` = `30m`
3. Pull the model: `ollama pull qwen3.5:9b` (about 6 GB). Fallback if memory is tight: `ollama pull qwen3.5:4b`.
4. Check it's on the GPU: run `ollama run qwen3.5:9b "say hi"`, then `ollama ps`: the PROCESSOR column should say `100% GPU`. If it says CPU, the driver or CUDA path is wrong.

Thinking mode: the pipeline turns thinking off per request (Qwen3.5 handles tool calls and structured output better without it on llama.cpp-based servers).

## 3. SearXNG (search, in Docker)

1. Install **Docker Desktop** (WSL2 backend).
2. Create a folder `C:\searxng` with a `settings.yml`:
   ```yaml
   use_default_settings: true
   server:
     secret_key: "<paste a long random string>"
     limiter: false
   search:
     formats: [html, json]
   ```
   `formats` must include `json` or the API returns 403.
3. Run it:
   ```
   docker run -d --name searxng --restart unless-stopped -p 8080:8080 -v C:\searxng:/etc/searxng searxng/searxng
   ```
4. Check: open `http://localhost:8080/search?q=green+bay+packers&format=json` in a browser on the desktop. You should get JSON results.

## 4. Tailscale (private network between your machines)

1. Install Tailscale on the desktop and sign in.
2. Install Tailscale on the laptop (Windows) and sign in with the same account.
3. Note the desktop's tailnet name or IP (`tailscale ip -4` on the desktop, e.g. `100.x.y.z`).
4. WSL on the laptop: if `curl http://100.x.y.z:11434` doesn't connect from WSL, enable WSL mirrored networking (`networkingMode=mirrored` in `%UserProfile%\.wslconfig`, then `wsl --shutdown`), or install Tailscale inside WSL.

## 5. Firewall (don't expose these to the internet)

In Windows Defender Firewall → Advanced → Inbound Rules, allow TCP **11434** (Ollama) and **8080** (SearXNG) **only from the Tailscale range `100.64.0.0/10`**. No router port forwarding.

## 6. Power

- Settings → System → Power: never sleep while plugged in during research nights, or use a scheduled wake (Task Scheduler "wake the computer to run this task").
- Expect roughly 60–80 W idle and 200–250 W while generating.

## 7. Smoke test from the laptop (WSL)

```
export LLM_BASE_URL=http://100.x.y.z:11434/v1
export SEARX_URL=http://100.x.y.z:8080

curl -s $LLM_BASE_URL/models | head
curl -s "$SEARX_URL/search?q=packers+injury+report&format=json" | head -c 400
curl -s $LLM_BASE_URL/chat/completions -H 'Content-Type: application/json' -d '{
  "model": "qwen3.5:9b",
  "messages": [{"role": "user", "content": "Reply with JSON: {\"ok\": true}"}],
  "response_format": {"type": "json_object"}
}'
```

All three should answer. Then put the two URLs in the project's `.env` (`LLM_BASE_URL`, `SEARX_URL`); the local research job (M6.2) reads them.

## Troubleshooting

- **`ollama ps` shows CPU:** driver older than 570 or a CUDA-13-only build; update to the 580 driver; check Ollama's release notes still list compute 6.1.
- **Out of memory / very slow:** drop `OLLAMA_CONTEXT_LENGTH` to 8192 or use `qwen3.5:4b`.
- **SearXNG returns few results:** some engines rate-limit; enable more engines in `settings.yml` or lower request frequency.
