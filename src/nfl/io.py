"""Safe parquet writes (ADR 0025).

`write_parquet` writes to a hidden temp file beside the target and renames it over the target, so a
crash mid-write leaves the old file whole on a local disk (on the jobs' Cloud Storage FUSE mount an
object only appears once its upload completes, so the rename adds nothing there but costs little).
The temp name doesn't end in `.parquet`, so no glob or catalog view ever reads one.

`append` is the one append-only write: the stored rows come first, untouched, then the new rows, both
cast to the table's declared schema. Every append-only mart that doesn't need a special rule (a
dedupe key, the backfill replacement in `predict.append_rows`) goes through it.
"""

from __future__ import annotations

import os
from pathlib import Path

import polars as pl


def _tmp(path: Path) -> Path:
    return path.with_name(f".{path.name}.{os.getpid()}.tmp")


def write_parquet(df: pl.DataFrame, path: Path) -> None:
    """Write `df` to `path` atomically (temp file, then rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = _tmp(path)
    try:
        df.write_parquet(tmp)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def read(path: Path, schema: dict[str, pl.DataType]) -> pl.DataFrame:
    """The stored table cast to `schema` (columns it lacks come back null), or an empty one."""
    if not path.exists():
        return pl.DataFrame(schema=schema)
    df = pl.read_parquet(path)
    for c, t in schema.items():
        if c not in df.columns:
            df = df.with_columns(pl.lit(None, dtype=t).alias(c))
    return df.select(list(schema)).cast(schema)


def append(path: Path, new: pl.DataFrame, schema: dict[str, pl.DataType]) -> int:
    """Append `new` after the stored rows, which are never edited or dropped. Returns rows added."""
    if new.is_empty():
        return 0
    old = read(path, schema)
    write_parquet(pl.concat([old, new.select(list(schema)).cast(schema)]), path)
    return new.height
