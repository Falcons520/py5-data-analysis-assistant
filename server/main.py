"""FastAPI 应用入口：REST 接口 + 静态前端。"""

from __future__ import annotations

import logging
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import L15
from . import config, pipeline, store
from .pipeline import AnalysisError
from .security import safe_filename

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,32}$")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("analysis-assistant")

MEDIA_TYPES = {
    "markdown": "text/markdown; charset=utf-8",
    "word": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "excel": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "summary": "text/plain; charset=utf-8",
}
FILE_SUFFIX = {"markdown": ".md", "word": ".docx", "excel": ".xlsx", "summary": ".txt"}
FILE_LABEL = {"markdown": "_分析报告", "word": "_报告", "excel": "_数据附件", "summary": "_摘要"}


@asynccontextmanager
async def lifespan(_: FastAPI):
    store.cleanup_expired(config.JOB_RETENTION_HOURS)
    logger.info(
        "AI 数据分析助手已启动 | model=%s | key=%s | data=%s",
        config.DEEPSEEK_MODEL,
        "已配置" if config.DEEPSEEK_API_KEY else "未配置",
        config.DATA_DIR,
    )
    yield


app = FastAPI(
    title="AI 数据分析助手",
    description="上传数据 → 自动清洗 → DeepSeek 智能分析 → 多格式报告导出",
    version="2.0.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS or ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AnalysisError)
async def analysis_error_handler(_, exc: AnalysisError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


# ── 请求模型 ────────────────────────────────────────────────────────────

class CleanOptions(BaseModel):
    fill_strategy: str = Field(default="auto", pattern="^(auto|mean|mode|drop)$")
    outlier_method: str = Field(default="iqr", pattern="^(iqr|zscore)$")
    remove_duplicates: bool = True


class AnalyzeRequest(BaseModel):
    dataset_id: str = Field(min_length=4, max_length=32)
    query: str = Field(min_length=1, max_length=2000)


class EmailRequest(BaseModel):
    sender: str = Field(min_length=3, max_length=200)
    auth_code: str = Field(min_length=1, max_length=200)
    receiver: str = Field(min_length=3, max_length=200)


# ── 基础接口 ────────────────────────────────────────────────────────────

@app.get("/api/health")
def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "version": "2.0.0",
        "model": config.DEEPSEEK_MODEL,
        "key_configured": bool(config.DEEPSEEK_API_KEY),
        "email_enabled": config.EMAIL_ENABLED,
    }


@app.post("/api/datasets")
async def upload_dataset(file: UploadFile = File(...)) -> Dict[str, Any]:
    name = pipeline_safe_name(file.filename)
    if not name.lower().endswith(pipeline.SUPPORTED_EXTENSIONS):
        raise HTTPException(400, "不支持的文件类型，请上传 CSV / Excel / JSON / TXT / TSV")

    raw = await file.read()
    if not raw:
        raise HTTPException(400, "文件为空")
    if len(raw) > config.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"文件超过 {config.MAX_UPLOAD_MB}MB 限制")

    df = pipeline.read_dataframe(name, raw)
    meta = store.create_dataset(name, df)
    return {
        "dataset": _dataset_payload(meta),
        "preview": pipeline.dataframe_preview(df),
    }


@app.post("/api/datasets/demo")
def create_demo_dataset() -> Dict[str, Any]:
    """用仓库自带的 lesson_data.csv 快速体验。"""
    source = config.BASE_DIR / "lesson_data.csv"
    if not source.exists():
        raise HTTPException(404, "示例数据不存在")
    df = pipeline.read_dataframe(source.name, source.read_bytes())
    meta = store.create_dataset("lesson_data.csv", df)
    return {
        "dataset": _dataset_payload(meta),
        "preview": pipeline.dataframe_preview(df),
    }


@app.get("/api/datasets/{dataset_id}")
def get_dataset(dataset_id: str) -> Dict[str, Any]:
    return _dataset_payload(_load_dataset(dataset_id))


@app.post("/api/datasets/{dataset_id}/clean")
def clean_dataset(dataset_id: str, options: CleanOptions) -> Dict[str, Any]:
    _load_dataset(dataset_id)
    return pipeline.clean_dataset(dataset_id, options.model_dump())


# ── 分析任务 ────────────────────────────────────────────────────────────

@app.post("/api/jobs")
def create_job(payload: AnalyzeRequest) -> Dict[str, Any]:
    _load_dataset(payload.dataset_id, "数据集不存在或已过期，请重新上传")

    query = payload.query.strip()
    if not query:
        raise HTTPException(400, "请输入分析需求")
    if not config.DEEPSEEK_API_KEY:
        raise HTTPException(503, "服务端未配置 DEEPSEEK_API_KEY，暂无法分析")

    store.cleanup_expired(config.JOB_RETENTION_HOURS)
    if store.running_job_count() >= config.MAX_CONCURRENT_JOBS:
        raise HTTPException(429, "当前分析任务较多，请稍后再试")

    job = store.create_job(payload.dataset_id, query)
    _start_job(job["id"], payload.dataset_id, query)
    return {"job_id": job["id"], "status": job["status"]}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> Dict[str, Any]:
    return _job_payload(_load_job(job_id))


@app.get("/api/jobs/{job_id}/chart/{filename}")
def get_chart(job_id: str, filename: str) -> FileResponse:
    if not filename.startswith("chart_") or not filename.endswith(".png") or "/" in filename:
        raise HTTPException(400, "非法文件名")
    _load_job(job_id, "任务不存在")
    path = store.job_dir(job_id) / "charts" / filename
    if not path.exists():
        raise HTTPException(404, "图表不存在")
    return FileResponse(path, media_type="image/png")


@app.get("/api/jobs/{job_id}/download/{kind}")
def download(job_id: str, kind: str) -> FileResponse:
    if kind not in MEDIA_TYPES:
        raise HTTPException(400, "未知的下载类型")
    job = _load_job(job_id)
    if not job.get("result"):
        raise HTTPException(404, "结果尚未生成")

    filename = job["result"].get("files", {}).get(kind)
    if not filename:
        raise HTTPException(404, "文件不存在")
    path = store.job_dir(job_id) / filename
    if not path.exists():
        raise HTTPException(404, "文件不存在")

    dataset = store.get_dataset(job["dataset_id"]) or {}
    base = Path(dataset.get("name") or "dataset").stem
    suffix = FILE_SUFFIX[kind]
    return FileResponse(
        path,
        media_type=MEDIA_TYPES[kind],
        filename=f"{base}{FILE_LABEL[kind]}{suffix}",
    )


@app.post("/api/jobs/{job_id}/email")
def send_report_email(job_id: str, payload: EmailRequest) -> Dict[str, Any]:
    if not config.EMAIL_ENABLED:
        raise HTTPException(403, "服务端已关闭邮件发送功能")
    job = _load_job(job_id, "任务不存在或已过期")
    if not job.get("result"):
        raise HTTPException(404, "结果尚未生成")

    result = job["result"]
    attachments: List[str] = []
    charts_dir = store.job_dir(job_id) / "charts"
    for chart in result.get("charts", []):
        path = charts_dir / chart
        if path.exists():
            attachments.append(str(path))

    email_data = {
        "subject": result.get("subject", "数据分析报告"),
        "content_text": result.get("short_summary", ""),
        "content_html": result.get("report_html", ""),
        "attachments": attachments,
    }
    try:
        L15.send_email(payload.sender, payload.auth_code, payload.receiver, email_data)
    except Exception as exc:  # 邮箱授权码错误等
        logger.warning("邮件发送失败: %s", exc)
        raise HTTPException(400, f"邮件发送失败：{exc}") from exc
    return {"ok": True, "receiver": payload.receiver, "attachments": len(attachments)}


# ── 内部工具 ────────────────────────────────────────────────────────────

def pipeline_safe_name(filename: Optional[str]) -> str:
    return safe_filename(filename or "dataset.csv", "dataset.csv")


def _check_id(value: str) -> str:
    """数据集 / 任务 id 只允许字母数字，防止路径穿越。"""
    if not _ID_RE.match(value or ""):
        raise HTTPException(404, "记录不存在或已过期")
    return value


def _load_dataset(dataset_id: str, message: str = "数据集不存在或已过期") -> Dict[str, Any]:
    meta = store.get_dataset(_check_id(dataset_id))
    if meta is None:
        raise HTTPException(404, message)
    return meta


def _load_job(job_id: str, message: str = "任务不存在或已过期") -> Dict[str, Any]:
    job = store.get_job(_check_id(job_id))
    if job is None:
        raise HTTPException(404, message)
    return job


def _dataset_payload(meta: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": meta["id"],
        "name": meta["name"],
        "rows": meta["rows"],
        "cols": meta["cols"],
        "columns": meta["columns"],
        "cleaned": meta.get("cleaned", False),
        "cleaned_rows": meta.get("cleaned_rows"),
        "cleaning_report": meta.get("cleaning_report", ""),
        "created_at": meta.get("created_at"),
    }


def _job_payload(job: Dict[str, Any]) -> Dict[str, Any]:
    payload = {
        "job_id": job["id"],
        "status": job.get("status", "queued"),
        "progress": job.get("progress", 0),
        "stage": job.get("stage", ""),
        "error": job.get("error", ""),
        "result": None,
    }
    result = job.get("result")
    if result:
        base = f"/api/jobs/{job['id']}"
        payload["result"] = {
            **result,
            "chart_urls": [f"{base}/chart/{name}" for name in result.get("charts", [])],
            "downloads": {
                kind: f"{base}/download/{kind}" for kind in result.get("files", {})
            },
        }
    return payload


def _start_job(job_id: str, dataset_id: str, query: str) -> None:
    import threading

    def worker() -> None:
        store.update_job(job_id, status="running", progress=2, stage="准备中")

        def on_progress(percent: int, stage: str) -> None:
            store.update_job(job_id, status="running", progress=percent, stage=stage)

        try:
            result = pipeline.run_analysis(
                dataset_id,
                query,
                config.DEEPSEEK_API_KEY,
                store.job_dir(job_id),
                on_progress=on_progress,
            )
            store.update_job(
                job_id,
                status="succeeded",
                progress=100,
                stage="完成",
                result=result,
                finished_at=time.time(),
            )
        except AnalysisError as exc:
            store.update_job(
                job_id, status="failed", stage="分析失败", error=str(exc), finished_at=time.time()
            )
        except Exception as exc:  # noqa: BLE001 - 任务线程需兜底
            logger.exception("任务 %s 执行失败", job_id)
            store.update_job(
                job_id,
                status="failed",
                stage="分析失败",
                error=f"分析失败：{exc}",
                finished_at=time.time(),
            )

    threading.Thread(target=worker, name=f"job-{job_id}", daemon=True).start()


# ── 静态前端 ────────────────────────────────────────────────────────────

if config.STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=config.STATIC_DIR / "assets"), name="assets")


@app.get("/")
def index():
    index_file = config.STATIC_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(500, "前端资源缺失")
    return FileResponse(index_file, media_type="text/html; charset=utf-8")
