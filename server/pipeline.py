"""分析流水线：文件解析 → 数据清洗 → AI 分析 → 报告与附件生成。"""

from __future__ import annotations

import io
import math
from pathlib import Path
from typing import Any, Callable, Dict, List

import pandas as pd

import L15
from data_cleaning import run_cleaning_pipeline
from report_generator import (
    build_excel,
    build_markdown,
    build_word,
    generate_short_summary,
)
from . import store
from .security import sanitize_html

SUPPORTED_EXTENSIONS = (".csv", ".tsv", ".txt", ".xlsx", ".xls", ".xlsm", ".json")

ProgressFn = Callable[[int, str], None]


class AnalysisError(Exception):
    """可直接展示给用户的业务错误。"""


# ── 文件解析与预览 ──────────────────────────────────────────────────────

def read_dataframe(filename: str, raw: bytes) -> pd.DataFrame:
    name = (filename or "").lower()
    buffer = io.BytesIO(raw)

    try:
        if name.endswith((".xlsx", ".xlsm")):
            df = pd.read_excel(buffer, engine="openpyxl")
        elif name.endswith(".xls"):
            df = pd.read_excel(buffer, engine="xlrd")
        elif name.endswith(".json"):
            df = pd.read_json(buffer)
        elif name.endswith(".tsv"):
            df = pd.read_csv(buffer, sep="\t")
        elif name.endswith(".txt"):
            df = pd.read_csv(buffer, sep=None, engine="python")
        else:
            df = pd.read_csv(buffer)
    except Exception as exc:  # 解析失败统一转成用户可读错误
        raise AnalysisError(f"文件解析失败：{exc}") from exc

    if df.empty:
        raise AnalysisError("文件内容为空，请检查数据后重新上传。")
    if df.shape[1] > 200:
        raise AnalysisError("列数超过 200，请先精简数据后再上传。")
    return df


def dataframe_preview(df: pd.DataFrame, limit: int = 10) -> List[List[Any]]:
    """转成前端可直接渲染的二维表格，NaN 统一为 None。"""
    rows: List[List[Any]] = []
    for record in df.head(limit).itertuples(index=False, name=None):
        row: List[Any] = []
        for value in record:
            if value is None or (isinstance(value, float) and math.isnan(value)):
                row.append(None)
            elif isinstance(value, float):
                row.append(round(value, 4))
            elif isinstance(value, (pd.Timestamp,)):
                row.append(value.strftime("%Y-%m-%d %H:%M:%S"))
            elif pd.isna(value):
                row.append(None)
            else:
                row.append(value if isinstance(value, (int, str, bool)) else str(value))
        rows.append(row)
    return rows


def dataframe_meta(df: pd.DataFrame) -> Dict[str, Any]:
    numeric_cols = list(df.select_dtypes(include="number").columns)
    return {
        "rows": int(df.shape[0]),
        "cols": int(df.shape[1]),
        "columns": [str(c) for c in df.columns],
        "numeric_cols": [str(c) for c in numeric_cols],
    }


# ── 数据清洗 ────────────────────────────────────────────────────────────

def clean_dataset(dataset_id: str, options: Dict[str, Any]) -> Dict[str, Any]:
    meta = store.get_dataset(dataset_id)
    if meta is None:
        raise AnalysisError("数据集不存在或已过期，请重新上传。")

    df = pd.read_csv(store.dataset_csv(dataset_id, cleaned=False), low_memory=False)
    cleaned_df, report = run_cleaning_pipeline(df, options=options or {})

    target = store.dataset_dir(dataset_id) / "cleaned.csv"
    cleaned_df.to_csv(target, index=False)

    store.update_dataset(
        dataset_id,
        cleaned=True,
        cleaned_rows=int(cleaned_df.shape[0]),
        cleaning_report=report,
    )
    return {
        "report": report,
        "rows": int(cleaned_df.shape[0]),
        "cols": int(cleaned_df.shape[1]),
        "preview": dataframe_preview(cleaned_df),
        "columns": [str(c) for c in cleaned_df.columns],
    }


# ── AI 分析 ─────────────────────────────────────────────────────────────

def _normalize_charts(chart_paths: Any) -> List[str]:
    if not chart_paths:
        return []
    if isinstance(chart_paths, (list, tuple)):
        return [str(p) for p in chart_paths if p]
    return [str(chart_paths)]


def run_analysis(
    dataset_id: str,
    query: str,
    api_key: str,
    workdir: Path,
    on_progress: ProgressFn = lambda percent, stage: None,
) -> Dict[str, Any]:
    """执行完整分析，产物写入 workdir，返回结果字典（不含 URL 前缀）。"""
    meta = store.get_dataset(dataset_id)
    if meta is None:
        raise AnalysisError("数据集不存在或已过期，请重新上传。")

    on_progress(5, "读取数据")
    csv_path = store.dataset_csv(dataset_id, cleaned=bool(meta.get("cleaned")))
    df = pd.read_csv(csv_path, low_memory=False)
    cleaning_report = meta.get("cleaning_report") or ""

    if not api_key:
        raise AnalysisError(
            "服务端未配置 DEEPSEEK_API_KEY，请在部署环境中设置后重试。"
        )

    charts_dir = workdir / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    on_progress(15, "AI 正在理解需求并分析数据")
    answer = L15.data_analyze_agent(
        str(csv_path), query, api_key, output_dir=str(charts_dir)
    )
    if not isinstance(answer, dict):
        raise AnalysisError("模型返回格式异常，请重试或换一种问法。")

    if answer.get("type") == "error":
        detail = (answer.get("data") or {}).get("message") or "模型无法根据当前数据完成分析。"
        suggestions = (answer.get("data") or {}).get("suggestions") or []
        if suggestions:
            detail += "\n建议：" + "；".join(str(s) for s in suggestions[:3])
        raise AnalysisError(detail)

    chart_files = []
    for index, path in enumerate(_normalize_charts(answer.get("chart_paths"))):
        source = Path(path)
        if source.exists():
            target = charts_dir / f"chart_{index + 1}.png"
            if source.resolve() != target.resolve():
                target.write_bytes(source.read_bytes())
            chart_files.append(target.name)

    on_progress(55, "生成结构化报告")
    report_data = L15.generate_report([answer], api_key)

    on_progress(70, "生成核心结论摘要")
    try:
        short_summary = generate_short_summary([answer], api_key)
    except Exception:
        # 摘要失败不应阻断整体流程，退化为从分析摘要截取
        raw_summary = (answer.get("data") or {}).get("summary", "")
        short_summary = raw_summary[:100]

    on_progress(80, "构建导出文件")
    markdown = build_markdown(report_data, answer, cleaning_report, query)
    word_bytes = build_word(report_data, answer, cleaning_report, query).getvalue()
    excel_bytes = build_excel(df, cleaning_report).getvalue()

    files = {
        "markdown": workdir / "report.md",
        "word": workdir / "report.docx",
        "excel": workdir / "data.xlsx",
        "summary": workdir / "summary.txt",
    }
    files["markdown"].write_text(markdown, encoding="utf-8")
    files["word"].write_bytes(word_bytes)
    files["excel"].write_bytes(excel_bytes)
    files["summary"].write_text(short_summary, encoding="utf-8")

    on_progress(95, "整理结果")
    return {
        "subject": report_data.get("subject") or "数据分析报告",
        "report_html": sanitize_html(report_data.get("content_html", "")),
        "short_summary": short_summary,
        "analysis_summary": (answer.get("data") or {}).get("summary", ""),
        "input": answer.get("input") or query,
        "chart_type": (answer.get("data") or {}).get("chart_type", ""),
        "charts": chart_files,
        "files": {key: path.name for key, path in files.items()},
        "cleaning_report": cleaning_report,
        "query": query,
    }
