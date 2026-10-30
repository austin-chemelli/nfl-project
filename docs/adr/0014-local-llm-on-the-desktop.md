# ADR 0014: Narrative research and previews run on a local open-weight model on the desktop

Status: accepted 2026-10-28; amended 2026-10-29 (no API fallback, below). Amends ADR 0007 (LLM layer: spend, model roles, retrieval) and pulls part of ADR 0008's self-hosting work (the desktop) forward.

## Context
Austin would rather run the LLM work on his spare desktop than pay for API credits. The desktop has a GTX 1070 (8 GB, Pascal, compute 6.1), a Ryzen 7 3700X, 16 GB RAM, and runs Windows. The jobs are batch, not latency-sensitive: narrative research for ~16 games twice a week (search, read, extract into the v2 record) and short game previews checked by the faithfulness validator. Research notes: `.notes/local-llm-research.md`.

Verified 2026-10-28:
- **Model.** Qwen3.5-9B at 4-bit (~5.6 GB) is the consensus pick for 8 GB cards in 2026 guides; Gemma 4 E4B and Qwen3.5-4B leave more context headroom; Granite 4.x 8B and Ministral 3 8B are Apache-2.0 alternatives. Nothing smaller and better appeared July–October 2026 (recent releases are large).
- **Pascal.** CUDA 13 dropped compute < 7.5. Ollama still supports compute 6.1 through its CUDA 12 path (driver ≥ 570 needed for 5.0–6.2 cards); llama.cpp still ships a CUDA 12.4 Windows build that includes sm_61. Pin to CUDA-12-based releases.
- **Tool calling on Qwen3.5 in llama.cpp** misbehaves with thinking enabled (tool calls inside the reasoning block); disabling thinking fixes it.
- **Search.** Brave's free API tier ended in early 2026 (metered, card required). Self-hosted SearXNG serves JSON results once `json` is enabled in `settings.yml`.

## Options
1. Hosted API (Sonnet 5.5 + web search), as ADR 0007 planned: best quality, ~$5–10/week.
2. **Local open-weight model on the desktop**, deterministic search and fetch in code, the model used only for structured extraction and writing.
3. Keep using the Claude Code skill (development producer) indefinitely: good quality, but manual and not a production pipeline.

## Decision
Option 2, with the API as a measured fallback, not a default.
- **Desktop stack (start on Windows, no reinstall):** NVIDIA driver 580 branch (the last with Pascal), Ollama serving **Qwen3.5-9B Q4_K_M** with thinking off, 16k context, q8_0 KV cache, listening only on the Tailscale interface; **SearXNG** in Docker with JSON enabled; **Tailscale** linking the laptop and the desktop. Moving the desktop to Ubuntu Server stays in the self-hosting project (ADR 0008).
- **No free-form agent.** Code does the searching (SearXNG), fetching and main-text extraction (with publish dates from page metadata). The model does small, schema-constrained steps: plan queries → extract facts per page (citing document ids, never URLs) → compose the v2 record (Ollama structured outputs with the JSON schema). Code maps document ids to URLs and dates, enforces the 10-day window, and runs the existing validator with retries. This removes URL hallucination and tool-calling fragility by construction.
- **Producer label `local`** (model name and quant in `model`), alongside `claude_code` and `api`; the pipeline treats them identically.
- **Previews (M6.3)** also run locally; the faithfulness check is the gate either way.
- **Quality is measured, not assumed:** before the local producer feeds the shadow Narrative approach, its records are compared with Claude-skill records on the same games (field agreement, claim overlap, citation validity, fabricated-claim rate). If it's clearly worse, the fallback is the Sonnet API job for research (previews can stay local).

## Consequences
LLM cost becomes electricity (~$1–5/month depending on idle policy) and runtime (estimated 10–20 minutes per game, i.e. a few hours per weekly run, overnight; unmeasured until the first run). The desktop must be on for research runs; until Cloud Scheduler (step 5), runs are triggered by hand or a Windows scheduled task. A small model will be worse than a frontier model at judgment ratings (sentiment, hype) and at synthesis across sources; the design keeps those as secondary, text-only fields and the comparison eval makes the gap visible. The weekly API cost cap stays in the code for the fallback path.

## Amendment 2026-10-29: no API fallback
Austin decided the app never uses a paid LLM API, including as a fallback. The M6.1 client talks only to the desktop's Ollama; it has no Anthropic code path, SDK dependency or cost cap. If the desktop is off or a run fails, LLM jobs fail and Austin gets an email; nothing reroutes. If the M6.2e comparison shows the local model is clearly worse, the options are a better local model or prompt, or keeping the Narrative approach on `/nfl-narrative` skill records (run by hand), not an API job. ADR 0007's spend target and weekly cap no longer apply.
