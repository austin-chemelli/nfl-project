"""LLM client and call log (M6.1; ADR 0007, ADR 0014).

Every LLM job goes through `LLMClient.complete`: one chat request to the desktop's model, optionally
constrained to a JSON schema (a pydantic model or a raw schema), with retries, and one row per
request appended to `marts/llm_calls.parquet`.

The only backend is the local OpenAI-compatible server at `LLM_BASE_URL` (Ollama on the desktop;
llama.cpp works too), model `LLM_MODEL`. There is no paid fallback (ADR 0014, amended 2026-10-29):
if the desktop is unreachable, calls fail. Thinking is off on every call (`reasoning_effort:
"none"`, because Ollama's /v1 ignores `think`); structured output via `response_format:
json_schema` (strict). Energy is estimated as latency x `LLM_LOCAL_WATTS`.

Retries: connection errors, timeouts, 429 and 5xx back off and retry; a reply that fails schema
validation is retried with the validation error appended to the conversation. Other 4xx and
truncated replies fail at once. Error strings in the log carry the status or exception type, never
a URL.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import polars as pl
from pydantic import BaseModel, ValidationError

from nfl.config import Paths, now_utc, snapshot_ts

LOCAL_MODEL = "qwen3.5:9b"
# Whole-desktop draw while generating (measured 200-250 W, docs/desktop-llm-setup.md §6).
LOCAL_WATTS = 225.0

LOG_SCHEMA: dict[str, Any] = {
    "run_id": pl.String,
    "job": pl.String,
    "model": pl.String,
    "prompt_version": pl.String,
    "game_id": pl.String,
    "attempt": pl.Int32,
    "ok": pl.Boolean,
    "error": pl.String,
    "input_tokens": pl.Int64,
    "output_tokens": pl.Int64,
    "cache_read_tokens": pl.Int64,
    "energy_wh": pl.Float64,
    "latency_ms": pl.Int64,
    "ts": pl.Datetime("us", "UTC"),
}


class LLMError(RuntimeError):
    pass


class _Transient(Exception):
    """A failure worth retrying after a backoff (network, timeout, 429, 5xx)."""


class _Invalid(Exception):
    """A reply that arrived but failed parsing or validation; retried with feedback."""


@dataclass(frozen=True)
class LLMConfig:
    model: str = LOCAL_MODEL
    base_url: str | None = None
    timeout_s: float = 300.0
    max_attempts: int = 3
    local_watts: float = LOCAL_WATTS

    @classmethod
    def from_env(cls, model: str | None = None) -> LLMConfig:
        return cls(
            model=model or os.environ.get("LLM_MODEL", LOCAL_MODEL),
            base_url=os.environ.get("LLM_BASE_URL") or None,
            timeout_s=float(os.environ.get("LLM_TIMEOUT_S", "300")),
            local_watts=float(os.environ.get("LLM_LOCAL_WATTS") or LOCAL_WATTS),
        )


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0


@dataclass
class Reply:
    text: str
    parsed: Any  # the pydantic instance, the decoded JSON for a raw schema, or None
    model: str
    usage: Usage
    latency_ms: int
    attempts: int


@dataclass
class _Attempt:
    text: str = ""
    model: str = ""
    usage: Usage = field(default_factory=Usage)
    truncated: bool = False


def calls_path(paths: Paths) -> Path:
    return paths.marts / "llm_calls.parquet"


def read_calls(paths: Paths) -> pl.DataFrame:
    p = calls_path(paths)
    return pl.read_parquet(p) if p.exists() else pl.DataFrame(schema=LOG_SCHEMA)


def append_call(paths: Paths, row: dict) -> None:
    """Append one row (the log is small: a few hundred rows a week). Written to a temp file and
    renamed, so a crash mid-write never truncates the log."""
    p = calls_path(paths)
    new = pl.DataFrame([row], schema=LOG_SCHEMA)
    if p.exists():
        new = pl.concat([pl.read_parquet(p), new], how="vertical_relaxed")
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".parquet.tmp")
    new.write_parquet(tmp)
    tmp.replace(p)


def _schema_of(schema: type[BaseModel] | dict | None) -> tuple[str, dict] | None:
    if schema is None:
        return None
    if isinstance(schema, dict):
        return "reply", schema
    return schema.__name__, schema.model_json_schema()


def _parse(text: str, schema: type[BaseModel] | dict | None) -> Any:
    if schema is None:
        return None
    try:
        if isinstance(schema, dict):
            return json.loads(text)
        return schema.model_validate_json(text)
    except (json.JSONDecodeError, ValidationError) as e:
        raise _Invalid(str(e).splitlines()[0][:300]) from None


class LLMClient:
    def __init__(
        self,
        paths: Paths,
        config: LLMConfig | None = None,
        *,
        run_id: str | None = None,
        http: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        log: bool = True,
    ):
        self.paths = paths
        self.config = config or LLMConfig.from_env()
        self.run_id = run_id or f"{snapshot_ts()}-{uuid.uuid4().hex[:6]}"
        self._http = http
        self._sleep = sleep
        self._log = log
        url = self.config.base_url or ""
        if not url or "<" in url:
            raise LLMError("LLM_BASE_URL is not set (.env; docs/desktop-llm-setup.md §7)")

    def complete(
        self,
        messages: list[dict],
        *,
        job: str,
        prompt_version: str,
        system: str | None = None,
        schema: type[BaseModel] | dict | None = None,
        game_id: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> Reply:
        cfg = self.config
        convo = list(messages)
        last_error = ""
        for attempt in range(1, cfg.max_attempts + 1):
            got = _Attempt(model=cfg.model)
            t0 = time.perf_counter()
            error: str | None = None
            parsed: Any = None
            retry_after: float | None = None
            try:
                got = self._send(system, convo, schema, max_tokens, temperature)
                if got.truncated:
                    raise LLMError(f"reply hit max_tokens={max_tokens}")
                parsed = _parse(got.text, schema)
            except _Transient as e:
                error = str(e)
                retry_after = min(2.0**attempt, 30.0)
            except _Invalid as e:
                error = f"invalid: {e}"
            except LLMError as e:
                error = str(e)
                self._record(job, prompt_version, game_id, attempt, got, t0, error)
                raise
            self._record(job, prompt_version, game_id, attempt, got, t0, error)
            if error is None:
                ms = int((time.perf_counter() - t0) * 1000)
                return Reply(got.text, parsed, got.model, got.usage, ms, attempt)
            last_error = error
            if retry_after is not None:
                if attempt < cfg.max_attempts:
                    self._sleep(retry_after)
            else:  # a reply that failed validation: show the model its mistake and ask again
                convo = convo + [
                    {"role": "assistant", "content": got.text},
                    {
                        "role": "user",
                        "content": f"That reply failed validation ({error}). "
                        "Reply again with only the corrected JSON.",
                    },
                ]
        raise LLMError(f"{job}: gave up after {cfg.max_attempts} attempts ({last_error})")

    def _record(self, job, prompt_version, game_id, attempt, got: _Attempt, t0, error) -> None:
        if not self._log:
            return
        ms = int((time.perf_counter() - t0) * 1000)
        u = got.usage
        append_call(
            self.paths,
            {
                "run_id": self.run_id,
                "job": job,
                "model": got.model or self.config.model,
                "prompt_version": prompt_version,
                "game_id": game_id,
                "attempt": attempt,
                "ok": error is None,
                "error": error,
                "input_tokens": u.input_tokens,
                "output_tokens": u.output_tokens,
                "cache_read_tokens": u.cache_read_tokens,
                "energy_wh": ms / 1000 * self.config.local_watts / 3600,
                "latency_ms": ms,
                "ts": now_utc(),
            },
        )

    def _send(self, system, messages, schema, max_tokens, temperature) -> _Attempt:
        cfg = self.config
        msgs = ([{"role": "system", "content": system}] if system else []) + messages
        body: dict[str, Any] = {
            "model": cfg.model,
            "messages": msgs,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "reasoning_effort": "none",
        }
        if (s := _schema_of(schema)) is not None:
            name, js = s
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": name, "schema": js, "strict": True},
            }
        http = self._http or httpx.Client()
        try:
            r = http.post(
                f"{cfg.base_url.rstrip('/')}/chat/completions",
                json=body,
                timeout=httpx.Timeout(cfg.timeout_s, connect=10.0),
            )
        except httpx.TimeoutException:
            raise _Transient("timeout") from None
        except httpx.TransportError as e:
            raise _Transient(type(e).__name__) from None
        finally:
            if self._http is None:
                http.close()
        if r.status_code == 429 or r.status_code >= 500:
            raise _Transient(f"HTTP {r.status_code}")
        if r.status_code >= 400:
            raise LLMError(f"HTTP {r.status_code}: {r.text[:200]}")
        d = r.json()
        choice = d["choices"][0]
        u = d.get("usage") or {}
        return _Attempt(
            text=choice["message"].get("content") or "",
            model=d.get("model", cfg.model),
            usage=Usage(
                input_tokens=u.get("prompt_tokens", 0),
                output_tokens=u.get("completion_tokens", 0),
                cache_read_tokens=(u.get("prompt_tokens_details") or {}).get("cached_tokens", 0),
            ),
            truncated=choice.get("finish_reason") == "length",
        )
