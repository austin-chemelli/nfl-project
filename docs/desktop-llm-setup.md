# Desktop LLM setup (Windows 10)

The spare desktop is the project's local LLM and search server (ADR 0014). This is what was actually set up on 2026-10-29 and how to check or redo it; the original plan was written 2026-10-28 and corrected where the hardware disagreed. Recheck the two version pins (driver, Ollama) if you redo this much later.

**What you end up with:** Ollama serving Qwen3.5-9B (and -4B as a fallback) and SearXNG serving JSON search results, both reachable only from your own devices over Tailscale. The pipeline calls them over the network from the laptop, or from the desktop's own WSL.

**Hardware this was verified on:** Ryzen 7 3700X, 16 GB RAM, GTX 1070 8 GB (Pascal, compute 6.1), Windows 10 Pro 22H2, WSL2 Ubuntu with Docker Desktop (WSL engine).

## 1. NVIDIA driver (Pascal-safe)

CUDA 13 dropped Pascal. The R580 driver branch is the last one that supports the GTX 1070; it now only gets security updates, and the newest build is **582.28** (Win10/Win11, "legacy" download page).

1. Install 582.28 (silent: `nvidia-....exe -s -noreboot -clean -noeula -nofinish`; it recommends a reboot afterwards).
2. Check: `nvidia-smi` shows driver 582.28, CUDA 13.0, GTX 1070 with 8192 MiB. Ollama ignores the driver's CUDA 13 and uses its own `cuda_v12` runner, which still lists compute 6.1.
3. Don't let a future driver update move the card off this branch; if a later install breaks `ollama ps` (shows CPU), roll back to 582.28.

## 2. Ollama and the models

Ollama for Windows (0.40.12 here) is a **tray app, not a service**: `ollama app.exe` starts at sign-in (shortcut in the Startup folder) and spawns `ollama.exe serve`. Nothing runs until someone signs in after a reboot.

1. Install Ollama from ollama.com.
2. Environment variables, **User** scope (System Properties → Environment Variables → User variables, or `setx` in a normal PowerShell):
   - `OLLAMA_HOST` = `0.0.0.0:11434` (listen on every interface; the firewall in §5 limits who can reach it)
   - `OLLAMA_CONTEXT_LENGTH` = `16384`
   - `OLLAMA_FLASH_ATTENTION` = `1`
   - `OLLAMA_KV_CACHE_TYPE` = `q8_0` (halves the context's memory; needs flash attention)
   - `OLLAMA_KEEP_ALIVE` = `30m`
3. Quit Ollama from the tray and start it again **from the Start menu** so it picks up the variables. (Starting it from a WSL shell or a script gives it a wrong environment and it never starts serving.) `%LOCALAPPDATA%\Ollama\server.log` should show `Listening on [::]:11434` and a `server config` line with the values above.
4. The first time it listens on the network, Windows shows its firewall prompt and creates per-app `ollama.exe` rules (Allow on Private, Block on Public). Delete those in the admin step of §5; the scoped port rule is the one we want.
5. Pull the models: `ollama pull qwen3.5:9b` (6.6 GB on disk) and `ollama pull qwen3.5:4b` (3.3 GB).
6. Check GPU residency: `ollama run qwen3.5:9b --think=false "say hi"`, then `ollama ps` must say `100% GPU` with `CONTEXT 16384`.

**Measured on the GTX 1070 (16k context, q8_0 KV, flash attention):**

| Model | `ollama ps` size | VRAM used / total | Generation | Prompt eval |
|---|---|---|---|---|
| qwen3.5:9b (default) | 5.8 GB | 6.9 / 8.0 GB | 23 tok/s | 206 tok/s |
| qwen3.5:4b (fallback) | 3.4 GB | 4.5 / 8.0 GB | 39 tok/s | 297 tok/s |

The 9B fits with about 1.2 GB of VRAM to spare; anything else using the GPU heavily (games, Wallpaper Engine on a video wallpaper) can push it partly to CPU, which `ollama ps` shows as a split percentage.

**Thinking mode.** Qwen3.5 thinks by default, and Ollama's OpenAI-compatible `/v1/chat/completions` **ignores a `think` field**. Turn thinking off per request with `"reasoning_effort": "none"` on `/v1`, or `"think": false` on the native `/api/chat`. Measured: the same JSON request cost 312 completion tokens with thinking on and 19 with it off, and the thinking text comes back in a `reasoning` field. Structured output: `response_format: {"type": "json_object"}` on `/v1`, or `format: <JSON schema>` on `/api/chat`.

## 3. SearXNG (search, in Docker under WSL)

Docker Desktop runs the Linux engine inside WSL2. The config goes in a **named Docker volume**, not a bind mount from the WSL home: Docker Desktop starts at sign-in before the Ubuntu distro is running, and a bind mount of a distro path then resolves to an empty directory, SearXNG writes a default `settings.yml` into it, and every `format=json` request returns 403 until the container is recreated (this happened on the first reboot).

1. In WSL, keep the source copy at `~/searxng/settings.yml`:
   ```yaml
   use_default_settings: true
   server:
     secret_key: "<openssl rand -hex 32>"
     limiter: false
     image_proxy: false
   search:
     formats: [html, json]
   ```
   `formats` must include `json` or the API returns 403.
2. Copy it into a named volume and run the container from that volume (repeat the copy after editing the file, then `docker restart searxng`):
   ```
   docker volume create searxng-config
   docker run --rm -v searxng-config:/cfg -v ~/searxng:/src:ro alpine sh -c 'cp /src/settings.yml /cfg/ && chown 977:977 /cfg/settings.yml'
   docker run -d --name searxng --restart unless-stopped -p 8080:8080 -v searxng-config:/etc/searxng searxng/searxng:latest
   ```
3. Check: `curl 'http://localhost:8080/search?q=green+bay+packers&format=json'` from WSL returns JSON. Docker Desktop publishes the port on Windows too, so it is also reachable at `http://<desktop-tailscale-ip>:8080`.
4. `--restart unless-stopped` only helps while Docker Desktop is running: Docker Desktop must start at sign-in (its entry in the Run key does that; the setting in Docker Desktop → General is "Start Docker Desktop when you sign in").

## 4. Tailscale (private network between your machines)

Tailscale is a WireGuard mesh: each signed-in device gets a stable `100.x.y.z` address reachable only from your other signed-in devices, from any network, with no router changes.

1. Install Tailscale on the desktop (winget `Tailscale.Tailscale`) and sign in. `tailscale status` prints the desktop's IP; put it in `.env` as the host for `LLM_BASE_URL` and `SEARX_URL`.
2. Install Tailscale on the laptop (Windows) and sign in with the same account.
3. **WSL on either machine:** Windows 10 has no WSL mirrored networking (that is Windows 11). Just call the desktop's Tailscale IP from WSL: outbound traffic leaves through Windows' Tailscale adapter, and this works on the desktop's own WSL too (verified). Don't use the WSL NAT gateway address (`172.x.x.1`); it changes every boot and the Block rule from §2 step 4 covers it anyway.

## 5. Firewall (don't expose these to the internet)

Admin PowerShell: allow TCP **11434** (Ollama) and **8080** (SearXNG) inbound only from the tailnet `100.64.0.0/10` and the WSL NAT range `172.16.0.0/12`, all profiles:

```powershell
foreach ($r in @(@{n='NFL local LLM - Ollama 11434'; p=11434}, @{n='NFL local LLM - SearXNG 8080'; p=8080})) {
  New-NetFirewallRule -DisplayName $r.n -Direction Inbound -Action Allow -Protocol TCP -LocalPort $r.p `
    -RemoteAddress @('100.64.0.0/10','172.16.0.0/12') -Profile Any
}
Remove-NetFirewallRule -DisplayName 'ollama.exe'   # the auto-created per-app rules from the Windows prompt
New-NetFirewallRule -DisplayName 'NFL local LLM - Ollama program' -Direction Inbound -Action Allow -Protocol TCP `
  -Program 'C:\Users\Austin\AppData\Local\Programs\Ollama\ollama.exe' -RemoteAddress @('100.64.0.0/10','172.16.0.0/12') -Profile Any
```

The auto-created rules matter: "Allow on Private from any address" would expose Ollama to the whole LAN if the Ethernet connection is ever set to Private. Deleting them alone is not enough: Windows shows the prompt again at the next sign-in and recreates them (seen after the first reboot). The scoped **program** rule is what stops the prompt, because Windows only asks when no rule names the executable. No router port forwarding.

## 6. Power

- Sleep and hibernate are set to never on AC (`powercfg`), hibernation file removed.
- Ollama and Docker Desktop start at **sign-in**, not at boot. After a Windows Update reboot the desktop sits at the lock screen with nothing serving until someone signs in. Options: accept it, or enable automatic sign-in (`netplwiz`) on this single-user machine.
- Expect roughly 60–80 W idle and 200–250 W while generating.

## 7. Smoke test from the laptop (WSL)

```
export LLM_BASE_URL=http://<desktop-tailscale-ip>:11434/v1
export SEARX_URL=http://<desktop-tailscale-ip>:8080

curl -s $LLM_BASE_URL/models | head
curl -s "$SEARX_URL/search?q=packers+injury+report&format=json" | head -c 400
curl -s $LLM_BASE_URL/chat/completions -H 'Content-Type: application/json' -d '{
  "model": "qwen3.5:9b",
  "messages": [{"role": "user", "content": "Reply with JSON: {\"ok\": true}"}],
  "response_format": {"type": "json_object"},
  "reasoning_effort": "none"
}'
```

All three should answer (the third in a few seconds once the model is loaded, ~20 s cold). Then put the two URLs and `LLM_MODEL=qwen3.5:9b` in the project's `.env`; the M6.1 client and the local research job (M6.2L) read them. Status 2026-10-29: all three pass from the desktop's WSL and from the laptop's WSL (Windows 11, WSL NAT mode, Tailscale on Windows only).

## Troubleshooting

- **`ollama ps` shows CPU or a split:** driver off the R580 branch, or VRAM taken by something else (check `nvidia-smi`). Close the GPU-heavy app, or use `qwen3.5:4b`.
- **Nothing on port 11434 after changing env vars:** the tray app was started from the wrong context (script, WSL). Quit it from the tray, start it from the Start menu, check `server.log`.
- **Reachable over Tailscale but not from WSL's NAT gateway:** expected; see §2 step 4 and §4 step 3.
- **Replies are slow and `completion_tokens` is large:** thinking is on. Send `reasoning_effort: "none"` (`/v1`) or `think: false` (`/api/chat`).
- **Out of memory / very slow:** drop `OLLAMA_CONTEXT_LENGTH` to 8192 or use `qwen3.5:4b`.
- **SearXNG returns few results:** some engines rate-limit; enable more engines in `settings.yml` or lower request frequency.
- **SearXNG down after a reboot:** Docker Desktop isn't running; start it (or fix its start-at-sign-in setting).
- **SearXNG answers HTML but `format=json` is 403 after a reboot:** the container is running a default `settings.yml`, which happens if its config is a bind mount from the WSL distro (see §3). Move the config to the named volume; as a stopgap, `docker restart searxng` once the distro is up.
