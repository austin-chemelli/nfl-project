"""LLM client: request shape, retries and the call log (stub server only)."""

from __future__ import annotations

import json

import httpx
import pytest
from pydantic import BaseModel

from nfl.config import Paths
from nfl.llm.client import (
    LLMClient,
    LLMConfig,
    LLMError,
    read_calls,
)

LOCAL = LLMConfig(base_url="http://desk:11434/v1", max_attempts=3)
MSG = [{"role": "user", "content": "hi"}]


class Team(BaseModel):
    team: str
    wins: int


def _ok(content: str, finish: str = "stop") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "model": "qwen3.5:9b",
            "choices": [
                {"message": {"role": "assistant", "content": content}, "finish_reason": finish}
            ],
            "usage": {"prompt_tokens": 12, "completion_tokens": 7},
        },
    )


def _client(tmp_path, responses, config=LOCAL, seen=None):
    queue = list(responses)

    def handler(req: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(json.loads(req.content))
        r = queue.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    http = httpx.Client(transport=httpx.MockTransport(handler))
    sleeps: list[float] = []
    c = LLMClient(Paths(tmp_path), config, run_id="r1", http=http, sleep=sleeps.append)
    return c, sleeps


def test_local_request_turns_thinking_off_and_sends_the_schema(tmp_path):
    seen: list[dict] = []
    c, _ = _client(tmp_path, [_ok('{"team": "GB", "wins": 9}')], seen=seen)
    r = c.complete(
        MSG, job="t", prompt_version="t_v1", system="be brief", schema=Team, game_id="g1"
    )
    assert r.parsed == Team(team="GB", wins=9) and r.attempts == 1
    body = seen[0]
    assert body["reasoning_effort"] == "none"
    assert body["messages"][0] == {"role": "system", "content": "be brief"}
    fmt = body["response_format"]
    assert fmt["type"] == "json_schema" and fmt["json_schema"]["strict"] is True
    assert fmt["json_schema"]["schema"]["required"] == ["team", "wins"]

    log = read_calls(Paths(tmp_path))
    row = log.row(0, named=True)
    assert log.height == 1 and row["ok"] and row["game_id"] == "g1" and row["run_id"] == "r1"
    assert (row["input_tokens"], row["output_tokens"]) == (12, 7)
    assert row["energy_wh"] > 0


def test_transient_errors_back_off_and_retry(tmp_path):
    c, sleeps = _client(
        tmp_path,
        [httpx.ConnectError("down"), httpx.Response(503), _ok('{"team": "GB", "wins": 1}')],
    )
    r = c.complete(MSG, job="t", prompt_version="v1", schema=Team)
    assert r.attempts == 3 and sleeps == [2.0, 4.0]
    log = read_calls(Paths(tmp_path))
    assert log["ok"].to_list() == [False, False, True]
    assert log["error"].to_list()[:2] == ["ConnectError", "HTTP 503"]


def test_invalid_reply_is_retried_with_the_error_shown_to_the_model(tmp_path):
    seen: list[dict] = []
    c, sleeps = _client(
        tmp_path, [_ok('{"team": "GB"}'), _ok('{"team": "GB", "wins": 2}')], seen=seen
    )
    r = c.complete(MSG, job="t", prompt_version="v1", schema=Team)
    assert r.parsed.wins == 2 and r.attempts == 2 and not sleeps
    retry = seen[1]["messages"]
    assert retry[-2] == {"role": "assistant", "content": '{"team": "GB"}'}
    assert "failed validation" in retry[-1]["content"]


def test_gives_up_after_max_attempts(tmp_path):
    c, _ = _client(tmp_path, [httpx.Response(500)] * 3)
    with pytest.raises(LLMError, match="gave up after 3"):
        c.complete(MSG, job="t", prompt_version="v1")
    assert read_calls(Paths(tmp_path)).height == 3


def test_client_errors_and_truncation_fail_at_once_but_are_logged(tmp_path):
    c, _ = _client(tmp_path, [httpx.Response(400, text="bad model")])
    with pytest.raises(LLMError, match="HTTP 400"):
        c.complete(MSG, job="t", prompt_version="v1")
    c, _ = _client(tmp_path, [_ok('{"team": "G', finish="length")])
    with pytest.raises(LLMError, match="max_tokens"):
        c.complete(MSG, job="t", prompt_version="v1", schema=Team)
    log = read_calls(Paths(tmp_path))
    assert log.height == 2 and log["output_tokens"].to_list() == [0, 7]


def test_raw_schema_returns_decoded_json(tmp_path):
    c, _ = _client(tmp_path, [_ok('{"ok": true}')])
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}
    assert c.complete(MSG, job="t", prompt_version="v1", schema=schema).parsed == {"ok": True}


def test_local_needs_a_base_url(tmp_path):
    with pytest.raises(LLMError, match="LLM_BASE_URL"):
        LLMClient(Paths(tmp_path), LLMConfig(base_url="http://<desktop-tailscale-ip>:11434/v1"))
