import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest

from nfl import io, joblock
from nfl.config import Paths
from nfl.features import store

SCHEMA = {"game_id": pl.Utf8(), "p": pl.Float64()}


def test_append_keeps_the_stored_rows_first_and_untouched(tmp_path):
    f = tmp_path / "t.parquet"
    io.append(f, pl.DataFrame({"game_id": ["A"], "p": [0.5]}), SCHEMA)
    before = pl.read_parquet(f)
    io.append(f, pl.DataFrame({"game_id": ["B"], "p": [0.7], "extra": [1]}), SCHEMA)
    after = pl.read_parquet(f)
    assert after.head(before.height).equals(before)
    assert after["game_id"].to_list() == ["A", "B"]
    assert io.append(f, pl.DataFrame(schema=SCHEMA), SCHEMA) == 0


def test_a_failed_write_leaves_the_old_file_and_no_temp(tmp_path, monkeypatch):
    f = tmp_path / "t.parquet"
    io.write_parquet(pl.DataFrame({"game_id": ["A"], "p": [0.5]}), f)

    def boom(self, path, *a, **k):
        Path(path).write_bytes(b"half")  # a partial temp file, then the crash
        raise OSError("disk full")

    monkeypatch.setattr(pl.DataFrame, "write_parquet", boom)
    with pytest.raises(OSError):
        io.write_parquet(pl.DataFrame({"game_id": ["B"], "p": [0.1]}), f)
    monkeypatch.undo()
    assert pl.read_parquet(f)["game_id"].to_list() == ["A"]
    assert [p.name for p in tmp_path.iterdir()] == ["t.parquet"]


def test_read_fills_columns_an_older_file_lacks(tmp_path):
    f = tmp_path / "t.parquet"
    pl.DataFrame({"game_id": ["A"]}).write_parquet(f)
    assert io.read(f, SCHEMA).to_dicts() == [{"game_id": "A", "p": None}]


def test_write_features_leaves_an_unchanged_file_alone(tmp_path):
    paths = Paths(tmp_path)
    t = datetime(2026, 11, 1, 12)
    rows = pl.DataFrame(
        [{"season": 2026, "week": 9, "game_id": "G", "side": "home", "feature": "form.x",
          "value": 1.0, "known_as_of": t, "source": "s", "version": "1"}],
        schema=store.FEATURE_SCHEMA,
    )  # fmt: skip
    store.write_features(paths, rows)
    f = paths.marts / "features" / "season=2026" / "form.parquet"
    stamp = f.stat().st_mtime_ns
    assert store.write_features(paths, rows) == 0  # the same rows again
    assert store.write_features(paths, rows.with_columns(pl.lit(t + timedelta(days=1)).alias("known_as_of"))) == 0  # fmt: skip
    assert f.stat().st_mtime_ns == stamp
    store.write_features(paths, rows.with_columns(pl.lit(2.0).alias("value")))  # a correction
    assert f.stat().st_mtime_ns != stamp
    assert pl.read_parquet(f)["value"].to_list() == [2.0]


class FakeStore:
    """GCS semantics for one object: create only if absent, delete by generation. `lose_response`
    makes the next create succeed but report a conflict, as a retried upload does."""

    def __init__(self, clock):
        self.clock = clock
        self.obj = None
        self.gen = 0
        self.lose_response = False
        self.delete_errors = 0

    def create(self, name, body):
        if self.obj:
            return None
        self.gen += 1
        self.obj = joblock.Held(self.gen, self.clock(), json.loads(body))
        if self.lose_response:
            self.lose_response = False
            return None
        return self.gen

    def get(self, name):
        return self.obj

    def delete(self, name, generation):
        if self.delete_errors:
            self.delete_errors -= 1
            raise ConnectionError("503")
        if not self.obj or self.obj.generation != generation:
            return False
        self.obj = None
        return True


class Clock:
    def __init__(self):
        self.t = datetime(2026, 11, 7, 17, 0, tzinfo=UTC)

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += timedelta(seconds=s)


def setup():
    clock = Clock()
    return FakeStore(clock), clock


def take(owner, st, clock, **k):
    return joblock.acquire(owner, st, now=clock, sleep=clock.sleep, log=lambda m: None, **k)


def test_one_holder_at_a_time_and_only_the_holder_releases():
    st, clock = setup()
    gen = take("site", st, clock)
    assert gen == 1 and st.obj.owner == "site"
    joblock.release(99, st, log=lambda m: None)  # someone else's generation
    assert st.obj is not None
    joblock.release(gen, st, log=lambda m: None)
    assert st.obj is None


def test_a_waiting_job_fails_after_the_wait_but_a_lock_job_proceeds():
    st, clock = setup()
    take("site", st, clock)
    with pytest.raises(TimeoutError):
        take("daily", st, clock)
    assert clock.t - datetime(2026, 11, 7, 17, 0, tzinfo=UTC) >= joblock.WAIT
    # still inside site's 35 minutes: proceeding runs without the lock and never steals it
    assert take("lock-sat", st, clock, proceed=True, wait=timedelta(minutes=5)) == 0
    assert st.obj.owner == "site"


def test_a_waiting_job_gets_the_lock_once_it_is_released():
    st, clock = setup()
    first = take("site", st, clock)

    def sleep_then_release(s):
        clock.sleep(s)
        joblock.release(first, st, log=lambda m: None)

    gen = joblock.acquire("lock-sat", st, now=clock, sleep=sleep_then_release, log=lambda m: None)
    assert gen == 2 and st.obj.owner == "lock-sat"


def test_a_lock_expires_with_its_jobs_timeout_and_is_taken_over():
    st, clock = setup()
    take("retro", st, clock)  # a 30-minute job, killed by Cloud Run without its exit trap
    clock.t += timedelta(minutes=34)
    with pytest.raises(TimeoutError):  # not expired yet: 30 + 5 minutes
        take("site", st, clock, wait=timedelta(seconds=1))
    clock.t += timedelta(minutes=2)
    msgs = []
    gen = joblock.acquire("lock-thu", st, now=clock, sleep=clock.sleep, log=msgs.append)
    assert st.obj.owner == "lock-thu" and gen == st.obj.generation
    assert "expired" in msgs[0]


def test_a_create_whose_response_was_lost_is_recognized_as_our_own():
    st, clock = setup()
    st.lose_response = True
    gen = take("lock-thu", st, clock)
    assert gen == 1 and st.obj.owner == "lock-thu"
    assert clock.t == datetime(2026, 11, 7, 17, 0, tzinfo=UTC)  # no waiting on itself


def test_a_lock_that_keeps_vanishing_still_respects_the_wait():
    class Flaky(FakeStore):
        def create(self, name, body):
            return None  # 412 every time ...

        def get(self, name):
            return None  # ... but never there to read

    clock = Clock()
    with pytest.raises(TimeoutError):
        take("daily", Flaky(clock), clock)
    assert take("lock-sat", Flaky(clock), clock, proceed=True) == 0


def test_release_retries_errors():
    st, clock = setup()
    gen = take("site", st, clock)
    st.delete_errors = 2
    joblock.release(gen, st, log=lambda m: None, sleep=lambda s: None)
    assert st.obj is None


def test_the_lock_timeouts_match_the_cloud_run_jobs():
    tf = (Path(__file__).resolve().parents[1] / "infra" / "jobs.tf").read_text()
    jobs = dict(re.findall(r'args = \["([a-z-]+)"[^}]*timeout = "(\d+)s"', tf))
    assert jobs, "no jobs parsed from infra/jobs.tf"
    for job, secs in jobs.items():
        if job == "narrative-check":
            continue  # read-only: takes no lock
        assert joblock.TIMEOUTS[job] == timedelta(seconds=int(secs)), job


def test_without_a_bucket_everything_is_a_no_op(monkeypatch):
    monkeypatch.delenv("NFL_DATA_BUCKET", raising=False)
    assert joblock.store_from_env() is None
    assert joblock.acquire("site", None) == 0
    joblock.release(0, None)


def test_the_cli_runs_without_the_lock_when_the_store_breaks_but_fails_on_a_timeout(monkeypatch):
    from typer.testing import CliRunner

    from nfl.cli import app

    class Broken:
        def create(self, name, body):
            raise RuntimeError("403 from GCS")

    monkeypatch.setattr(joblock, "store_from_env", lambda: Broken())
    r = CliRunner().invoke(app, ["joblock", "acquire", "daily"])
    assert r.exit_code == 0 and r.stdout.strip().endswith("0")

    def timeout(*a, **k):
        raise TimeoutError("held by lock-sat")

    monkeypatch.setattr(joblock, "acquire", timeout)
    assert CliRunner().invoke(app, ["joblock", "acquire", "daily"]).exit_code == 1


def test_last_bit_float_noise_is_not_a_change_but_a_real_difference_is():
    a = pl.DataFrame({"game_id": ["G", "H"], "value": [0.1 + 0.2, None]})
    assert store._unchanged(a, a.with_columns(pl.Series("value", [0.3, None])))
    assert not store._unchanged(a, a.with_columns(pl.Series("value", [0.3001, None])))
    assert not store._unchanged(a, a.with_columns(pl.Series("value", [0.3, 1.0])))
    assert not store._unchanged(a, a.head(1))
