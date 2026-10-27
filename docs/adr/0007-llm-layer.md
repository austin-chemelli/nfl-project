# ADR 0007: LLM layer: API key, model roles, narrative live-only, native web search, parquet call log

Status: accepted 2026-10-23, revised 2026-10-25 for v2.

## Context
Claude Max covers Claude Code and claude.ai; subscription OAuth may not power an application (enforced server-side since ~Apr 2026). Web search cannot be backtested fairly. The LLM must not introduce numbers.

## Decision
- Spend: Anthropic Console API key, pay-as-you-go; Message Batches for non-urgent jobs; prompt caching on stable prompts. Target $10–15/week, hard cap $25/week enforced by per-run cost logging.
- Roles: Sonnet 5.5 for narrative extraction (web-search heavy); Opus 5.5 for game previews; Haiku 5.5 for judges and classification.
- Jobs, kept separate in code and prompts: (1) narrative feature extraction, structured, cited, prompt-versioned, live only, feeding the Narrative approach and the feature store; (2) preview text from feature contributions and tendencies, every number checked by a deterministic faithfulness pass before publishing; (3) concept explanations, labeled as general knowledge. The coordinator-table extraction is the first research eval but is offseason work.
- Retrieval: Anthropic's built-in web search tool with domain allow-lists for structured facts; log every query, URL and claim. No LangChain/LangGraph; Anthropic SDK directly.
- Observability: one parquet row per call (model, prompt version, tokens, cache tokens, cost, latency, run id). OTel to Cloud Monitoring with P2 for failure and freshness alerts. No Langfuse unless a trace UI is wanted.

## Consequences
The Narrative approach has no backtest; its record starts at its first live week and the UI must show "weeks tracked". Prompt changes mid-season create a new feature `version`. Cost becomes a published metric.
