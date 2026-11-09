"""数据集与任务的文件存储层。

所有状态落盘到 DATA_DIR 下，进程重启后仍可读取；内存只做缓存。
"""

from __future__ import annotations

import json
import os
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from . import config

DATASET_DIR = config.DATA_DIR / "datasets"
JOB_DIR = config.DATA_DIR / "jobs"

_lock = threading.RLock()
_datasets: Dict[str, Dict[str, Any]] = {}
_jobs: Dict[str, Dict[str, Any]] = {}


def _ensure_dirs() -> None:
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    JOB_DIR.mkdir(parents=True, exist_ok=True)


_ensure_dirs()


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def new_id() -> str:
    return uuid.uuid4().hex[:12]


# ── 数据集 ──────────────────────────────────────────────────────────────

def dataset_dir(dataset_id: str) -> Path:
    return DATASET_DIR / dataset_id


def create_dataset(name: str, df) -> Dict[str, Any]:
    ds_id = new_id()
    directory = dataset_dir(ds_id)
    directory.mkdir(parents=True, exist_ok=True)
    df.to_csv(directory / "raw.csv", index=False)

    meta = {
        "id": ds_id,
        "name": name,
        "rows": int(df.shape[0]),
        "cols": int(df.shape[1]),
        "columns": [str(c) for c in df.columns],
        "created_at": time.time(),
        "cleaned": False,
        "cleaned_rows": None,
        "cleaning_report": "",
        "chart_type": "",
    }
    _write_json(directory / "meta.json", meta)
    with _lock:
        _datasets[ds_id] = meta
    return meta


def get_dataset(dataset_id: str) -> Optional[Dict[str, Any]]:
    with _lock:
        cached = _datasets.get(dataset_id)
    if cached is not None:
        return cached
    meta = _read_json(dataset_dir(dataset_id) / "meta.json")
    if meta is not None:
        with _lock:
            _datasets[dataset_id] = meta
    return meta


def update_dataset(dataset_id: str, **changes) -> Dict[str, Any]:
    meta = get_dataset(dataset_id)
    if meta is None:
        raise KeyError(dataset_id)
    meta = {**meta, **changes}
    _write_json(dataset_dir(dataset_id) / "meta.json", meta)
    with _lock:
        _datasets[dataset_id] = meta
    return meta


def dataset_csv(dataset_id: str, cleaned: bool = False) -> Path:
    directory = dataset_dir(dataset_id)
    if cleaned and (directory / "cleaned.csv").exists():
        return directory / "cleaned.csv"
    return directory / "raw.csv"


# ── 任务 ────────────────────────────────────────────────────────────────

def job_dir(job_id: str) -> Path:
    return JOB_DIR / job_id


def create_job(dataset_id: str, query: str) -> Dict[str, Any]:
    job_id = new_id()
    directory = job_dir(job_id)
    directory.mkdir(parents=True, exist_ok=True)

    meta = {
        "id": job_id,
        "dataset_id": dataset_id,
        "query": query,
        "status": "queued",
        "progress": 0,
        "stage": "排队中",
        "error": "",
        "created_at": time.time(),
        "finished_at": None,
        "result": None,
    }
    _write_json(directory / "meta.json", meta)
    with _lock:
        _jobs[job_id] = meta
    return meta


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    with _lock:
        cached = _jobs.get(job_id)
    if cached is not None:
        return cached
    meta = _read_json(job_dir(job_id) / "meta.json")
    if meta is not None:
        with _lock:
            _jobs[job_id] = meta
    return meta


def update_job(job_id: str, **changes) -> Dict[str, Any]:
    with _lock:
        meta = _jobs.get(job_id)
    if meta is None:
        meta = _read_json(job_dir(job_id) / "meta.json")
    if meta is None:
        raise KeyError(job_id)
    meta = {**meta, **changes}
    _write_json(job_dir(job_id) / "meta.json", meta)
    with _lock:
        _jobs[job_id] = meta
    return meta


def running_job_count() -> int:
    with _lock:
        return sum(1 for job in _jobs.values() if job.get("status") in ("queued", "running"))


def cleanup_expired(older_than_hours: int) -> int:
    """删除超过保留期的数据集与任务目录，返回清理数量。"""
    if older_than_hours <= 0:
        return 0
    deadline = time.time() - older_than_hours * 3600
    removed = 0
    for base in (DATASET_DIR, JOB_DIR):
        if not base.exists():
            continue
        for child in base.iterdir():
            if not child.is_dir():
                continue
            try:
                if child.stat().st_mtime < deadline:
                    shutil.rmtree(child, ignore_errors=True)
                    removed += 1
            except OSError:
                continue
    if removed:
        with _lock:
            _datasets.clear()
            _jobs.clear()
    return removed
