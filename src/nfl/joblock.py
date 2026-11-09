"""One job at a time on the data (ADR 0025).

Every Cloud Run job that writes the data bucket takes this lock first (`scripts/cloud-job.sh`), so two
jobs can't interleave read-modify-write cycles: e.g. the `nfl-site` run the desktop starts after its
Saturday narrative pass rebuilding the site JSON from data read before the 12:00 lock wrote its
predictions, and overwriting the lock's site files.

The lock is one object, `locks/jobs.lock`, created with a generation precondition (`ifGenerationMatch=0`:
only one creator can succeed) and deleted by generation on release, so a job only ever releases its own
lock. Its body holds a random nonce, so a job whose create succeeded but whose response was lost (the
client retries, then sees 412) recognizes its own lock instead of waiting on it, and an `expires` time:
taking the lock + the job's Cloud Run timeout + a margin. Cloud Run has killed the holder by then
(a timed-out or cancelled job never runs its exit trap), so an expired lock is abandoned and taken over.

A waiting job polls until `WAIT`, then fails, or, for the lock jobs, proceeds with a warning, since a
missed lock is worse than a rare race. Without `NFL_DATA_BUCKET` (laptop, desktop, tests) there is
nothing to lock and every call is a no-op.
"""

from __future__ import annotations

import json
import os
import secrets
import socket
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Protocol

NAME = "locks/jobs.lock"
# cloud-job.sh job -> its Cloud Run timeout (infra/jobs.tf; a test keeps them equal)
TIMEOUTS = {
    "refresh": timedelta(hours=2),
    "lock": timedelta(hours=1),
    "odds": timedelta(minutes=30),
    "daily": timedelta(hours=1),
    "retro": timedelta(minutes=30),
    "site": timedelta(minutes=30),
}
MARGIN = timedelta(minutes=5)
STALE = max(TIMEOUTS.values()) + MARGIN  # a lock without an expiry (none should exist)
WAIT = timedelta(minutes=20)  # jobs take 2-11 min (2026-11); the shortest timeout is 30
POLL = 15.0
RELEASE_TRIES = 4


def _stderr(m: str) -> None:
    print(m, file=sys.stderr)


@dataclass
class Held:
    generation: int
    created: datetime
    body: dict = field(default_factory=dict)

    @property
    def owner(self) -> str:
        return self.body.get("owner", "?")

    def expires(self) -> datetime:
        try:
            return datetime.fromisoformat(self.body["expires"])
        except KeyError, TypeError, ValueError:
            return self.created + STALE


class Store(Protocol):
    def create(self, name: str, body: str) -> int | None: ...  # generation, or None if it exists
    def get(self, name: str) -> Held | None: ...
    def delete(self, name: str, generation: int) -> bool: ...  # False if it changed or is gone


class GcsStore:
    def __init__(self, bucket: str):
        from google.cloud import storage

        self.bucket = storage.Client().bucket(bucket)

    def create(self, name: str, body: str) -> int | None:
        from google.api_core.exceptions import PreconditionFailed

        blob = self.bucket.blob(name)
        try:
            blob.upload_from_string(body, content_type="application/json", if_generation_match=0)
        except PreconditionFailed:
            return None
        return int(blob.generation)

    def get(self, name: str) -> Held | None:
        from google.api_core.exceptions import NotFound

        blob = self.bucket.get_blob(name)
        if blob is None:
            return None
        try:
            body = json.loads(blob.download_as_text(if_generation_match=blob.generation))
        except NotFound:
            return None  # released between the two calls
        except Exception:  # noqa: BLE001 - a lock we can't read is still a lock
            body = {}
        return Held(int(blob.generation), blob.time_created, body if isinstance(body, dict) else {})

    def delete(self, name: str, generation: int) -> bool:
        from google.api_core.exceptions import NotFound, PreconditionFailed

        try:
            self.bucket.blob(name).delete(if_generation_match=generation)
        except PreconditionFailed, NotFound:
            return False
        return True


def store_from_env() -> Store | None:
    bucket = os.environ.get("NFL_DATA_BUCKET")
    return GcsStore(bucket) if bucket else None


def ttl(owner: str) -> timedelta:
    """How long `owner` ("lock-thu", "site", ...) can hold the lock: its job's timeout + MARGIN."""
    return TIMEOUTS.get(owner.split("-", 1)[0], max(TIMEOUTS.values())) + MARGIN


def acquire(
    owner: str,
    store: Store | None,
    *,
    wait: timedelta = WAIT,
    proceed: bool = False,
    poll: float = POLL,
    now=lambda: datetime.now(UTC),
    sleep=time.sleep,
    log=_stderr,
) -> int:
    """Take the lock; returns its generation (0 when there is no store or `proceed` gave up waiting).
    Raises TimeoutError after `wait` unless `proceed`."""
    if store is None:
        return 0
    nonce = secrets.token_hex(8)
    start = now()

    def waited_out(why: str) -> int:
        msg = f"joblock: {why}; waited {now() - start}"
        if proceed:
            log(msg + ", proceeding without it")
            return 0
        raise TimeoutError(msg)

    while True:
        t = now()
        body = {"owner": owner, "nonce": nonce, "host": socket.gethostname(),
                "at": t.isoformat(), "expires": (t + ttl(owner)).isoformat()}  # fmt: skip
        gen = store.create(NAME, json.dumps(body))
        if gen is not None:
            return gen
        held = store.get(NAME)
        if held is not None and held.body.get("nonce") == nonce:
            return held.generation  # our own create went through; its response didn't
        if held is None:  # released between our create and get
            if now() - start >= wait:
                return waited_out("the lock kept changing hands")
            sleep(1.0)
            continue
        if now() > held.expires():
            log(f"joblock: {held.owner}'s lock expired at {held.expires()}, taking it over")
            store.delete(NAME, held.generation)
            continue
        if now() - start >= wait:
            return waited_out(f"{held.owner} has held the data lock for {now() - held.created}")
        log(f"joblock: waiting for {held.owner} (held {now() - held.created})")
        sleep(poll)


def release(generation: int, store: Store | None, log=_stderr, sleep=time.sleep) -> None:
    """Release a lock this job took (generation from `acquire`); 0 is a no-op. Retries errors a few
    times: an unreleased lock blocks the next job until it expires."""
    if store is None or not generation:
        return
    for i in range(RELEASE_TRIES):
        try:
            if not store.delete(NAME, generation):
                log("joblock: the lock was already gone or taken over; nothing released")
            return
        except Exception as e:  # noqa: BLE001
            log(f"joblock: release failed ({e!r}), try {i + 1} of {RELEASE_TRIES}")
            sleep(2.0 * (i + 1))
    log("joblock: COULD NOT RELEASE the data lock; it blocks other jobs until it expires")
