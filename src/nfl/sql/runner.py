"""SQL models (ADR 0025, ADR 0026): `src/nfl/sql/models/<name>.sql` -> `marts/derived/<name>.parquet`.

Each model is one SELECT over the catalog's views (`catalog.connect`). The runner writes the result
with `nfl.io.write_parquet` and a sidecar `marts/derived/<name>.json` holding the SQL file's sha256 and
the row count (the model's source hash: it says which SQL produced the parquet). An unchanged result is
not rewritten, so the file's mtime and any downstream cache stay put; if only the SQL text changed, the
sidecar alone is updated. The catalog serves the result as a view named `<name>`.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import polars as pl
from polars.testing import assert_frame_equal

from nfl import catalog, io
from nfl.config import Paths

MODELS_DIR = Path(__file__).parent / "models"


@dataclass(frozen=True)
class BuildResult:
    name: str
    rows: int
    status: str  # written | unchanged | sql changed, output unchanged


def model_names() -> list[str]:
    return sorted(p.stem for p in MODELS_DIR.glob("*.sql"))


def sql_hash(name: str) -> str:
    return hashlib.sha256((MODELS_DIR / f"{name}.sql").read_bytes()).hexdigest()


def output_path(paths: Paths, name: str) -> Path:
    return paths.marts / "derived" / f"{name}.parquet"


def sidecar_path(paths: Paths, name: str) -> Path:
    return paths.marts / "derived" / f"{name}.json"


def _sidecar_hash(paths: Paths, name: str) -> str | None:
    p = sidecar_path(paths, name)
    if not p.exists():
        return None
    return json.loads(p.read_text()).get("sql_sha256")


def _same(old: pl.DataFrame, new: pl.DataFrame) -> bool:
    """Equal frames, floats to 1e-9 relative (DuckDB sums in parallel, so the last bits can vary)."""
    try:
        assert_frame_equal(old, new, check_exact=False, rel_tol=1e-9, abs_tol=1e-12)
    except AssertionError:
        return False
    return True


def build(paths: Paths, only: str | None = None) -> list[BuildResult]:
    """Build every model (or `only` one); returns what happened to each."""
    names = model_names()
    if only is not None:
        if only not in names:
            raise ValueError(f"no model {only!r}; have {', '.join(names)}")
        names = [only]
    out = []
    for name in names:
        con = catalog.connect(paths)
        df = con.sql((MODELS_DIR / f"{name}.sql").read_text()).pl()
        target, h = output_path(paths, name), sql_hash(name)
        same = target.exists() and _same(pl.read_parquet(target), df)
        if same and _sidecar_hash(paths, name) == h:
            status = "unchanged"
        else:
            if not same:
                io.write_parquet(df, target)
                status = "written"
            else:
                status = "sql changed, output unchanged"
            sidecar_path(paths, name).write_text(
                json.dumps({"sql_sha256": h, "rows": df.height}, indent=2) + "\n"
            )
        out.append(BuildResult(name, df.height, status))
    return out
