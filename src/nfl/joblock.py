"""One job at a time on the data (ADR 0025).

Every Cloud Run job that writes the data bucket takes this lock first (`scripts/cloud-job.sh`), so two
jobs can't interleave read-modify-write cycles: e.g. the `nfl-site` run the desktop starts after its
Saturday narrative pass rebuilding the site JSON from data read before the 12:00 lock wrote its
predictions, and overwriting the lock's site files.

The lock is one object, `locks/jobs.lock`, created with a generation precondition (`ifGenerationMatch=0`:
only one creator can succeed) and deleted by generation on release, so a job can only release its own
lock. A lock older than `STALE` (longer than the longest job timeout) is abandoned: a job that died
without its exit trap. A waiting job polls until `WAIT`, then fails, or, for the lock jobs, proceeds
with a warning, since a missed lock is worse than a rare race.

Without `NFL_DATA_BUCKET` (laptop, desktop, tests) there is nothing to lock and every call is a no-op.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

NAME = "locks/jobs.lock"
STALE = timedelta(hours=2, minutes=15)  # refresh's timeout is 2 h
WAIT = timedelta(minutes=20)  # jobs take 2-11 min (2026-11); the shortest timeout is 30
POLL = 15.0


@dataclass
class Held:
    generation: int
    owner: str
    created: datetime


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
        blob = self.bucket.get_blob(name)
        if blob is None:
            return None
        try:
            owner = json.loads(blob.download_as_text()).get("owner", "?")
        except Exception:  # noqa: BLE001 - a lock we can't read is still a lock
            owner = "?"
        return Held(int(blob.generation), owner, blob.time_created)

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


def acquire(
    owner: str,
    store: Store | None,
    *,
    wait: timedelta = WAIT,
    proceed: bool = False,
    poll: float = POLL,
    now=lambda: datetime.now(UTC),
    sleep=time.sleep,
    log=lambda m: print(m, file=sys.stderr),
) -> int:
    """Take the lock; returns its generation (0 when there is no store or `proceed` gave up waiting).
    Raises TimeoutError after `wait` unless `proceed`."""
    if store is None:
        return 0
    body = json.dumps({"owner": owner, "host": socket.gethostname(), "at": now().isoformat()})
    start = now()
    while True:
        gen = store.create(NAME, body)
        if gen is not None:
            return gen
        held = store.get(NAME)
        if held is None:
            continue  # released between our create and get: try again at once
        age = now() - held.created
        if age > STALE:
            log(f"joblock: {held.owner}'s lock is {age} old, taking it over as abandoned")
            store.delete(NAME, held.generation)
            continue
        if now() - start >= wait:
            msg = f"joblock: {held.owner} has held the data lock for {age}; waited {wait}"
            if proceed:
                log(msg + ", proceeding without it")
                return 0
            raise TimeoutError(msg)
        log(f"joblock: waiting for {held.owner} (held {age})")
        sleep(poll)


def release(generation: int, store: Store | None, log=lambda m: print(m, file=sys.stderr)) -> None:
    """Release a lock this job took (generation from `acquire`); 0 is a no-op."""
    if store is None or not generation:
        return
    if not store.delete(NAME, generation):
        log("joblock: the lock was already gone or taken over; nothing released")
