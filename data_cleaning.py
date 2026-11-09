"""
数据清洗模块：自动检测缺失值、重复值、异常值、格式问题，执行清洗并输出报告。
"""

import pandas as pd
import numpy as np
from io import StringIO


def detect_missing(df):
    """检测每列的缺失值数量与占比"""
    result = {}
    for col in df.columns:
        n_missing = int(df[col].isna().sum())
        if n_missing > 0:
            result[col] = {
                "count": n_missing,
                "ratio": round(n_missing / len(df) * 100, 2),
            }
    return result


def detect_duplicates(df):
    """检测完全重复的行"""
    dup_mask = df.duplicated(keep=False)
    dup_count = int(dup_mask.sum())
    dup_rows = int(df.duplicated().sum())
    return {
        "total_duplicate_cells": dup_count,
        "duplicate_rows": dup_rows,
        "ratio": round(dup_rows / len(df) * 100, 2),
    }


def detect_outliers(df, method="iqr"):
    """检测数值列中的异常值（IQR 或 Z-score 方法）"""
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    result = {}
    for col in numeric_cols:
        series = df[col].dropna()
        if len(series) < 4:
            continue
        if method == "iqr":
            Q1 = float(series.quantile(0.25))
            Q3 = float(series.quantile(0.75))
            IQR = Q3 - Q1
            lower = Q1 - 1.5 * IQR
            upper = Q3 + 1.5 * IQR
            outlier_mask = (df[col] < lower) | (df[col] > upper)
            n = int(outlier_mask.sum())
        else:  # z-score
            z = np.abs((series - series.mean()) / series.std())
            outlier_mask = z > 3
            n = int(outlier_mask.sum())
        if n > 0:
            result[col] = {
                "count": n,
                "ratio": round(n / len(df) * 100, 2),
                "lower_bound": round(lower, 4) if method == "iqr" else None,
                "upper_bound": round(upper, 4) if method == "iqr" else None,
            }
    return result


def detect_format_issues(df):
    """检测格式问题：前后空白、列名不规范、混合类型等"""
    issues = []
    for col in df.columns:
        # 列名含空格或特殊字符
        if " " in col or any(c in col for c in "!@#$%^&*()+={}[]|\\:;\"'<>?,/"):
            issues.append({"column": col, "issue": "列名含空格或特殊字符"})
        # object 列检测前后空白
        if df[col].dtype == object:
            str_series = df[col].dropna().astype(str)
            whitespace_count = int((str_series != str_series.str.strip()).sum())
            if whitespace_count > 0:
                issues.append({
                    "column": col,
                    "issue": "存在前后空白",
                    "count": whitespace_count,
                })
    return issues


def clean_dataframe(
    df,
    fill_missing=True,
    fill_strategy="auto",
    remove_duplicates=True,
    handle_outliers=True,
    outlier_method="iqr",
    trim_whitespace=True,
    clean_column_names=True,
):
    """
    对 DataFrame 执行清洗，返回 (cleaned_df, report_actions)。

    fill_strategy: "auto" → 数值列用均值、类别列用众数
                   "mean"  → 数值列用均值
                   "mode"  → 全部用众数
                   "drop"  → 删除含缺失值的行
    """
    df = df.copy()
    actions = []

    # 1. 列名清洗
    if clean_column_names:
        old_names = list(df.columns)
        new_names = []
        for name in old_names:
            new_name = str(name).strip().replace(" ", "_")
            for ch in "!@#$%^&*()+={}[]|\\:;\"'<>?,/":
                new_name = new_name.replace(ch, "_")
            new_names.append(new_name)
        if old_names != new_names:
            df.columns = new_names
            actions.append({
                "action": "列名规范化",
                "detail": f"修正 {sum(1 for o, n in zip(old_names, new_names) if o != n)} 个列名",
            })

    # 2. 去除前后空白
    if trim_whitespace:
        trimmed_count = 0
        for col in df.select_dtypes(include=["object"]).columns:
            mask = df[col].notna()
            series = df.loc[mask, col].astype(str)
            stripped = series.str.strip()
            needs_trim = series != stripped
            if needs_trim.any():
                df.loc[mask, col] = stripped
                trimmed_count += int(needs_trim.sum())
        if trimmed_count > 0:
            actions.append({
                "action": "去除前后空白",
                "detail": f"{trimmed_count} 个单元格已修剪",
            })

    # 3. 缺失值处理
    missing = detect_missing(df)
    if missing and fill_missing:
        for col, info in missing.items():
            if fill_strategy == "drop":
                continue
            if fill_strategy == "auto":
                if df[col].dtype in (np.float64, np.int64, float, int):
                    fill_val = df[col].mean()
                    label = f"均值({round(fill_val, 2)})"
                else:
                    mode_vals = df[col].mode()
                    fill_val = mode_vals[0] if len(mode_vals) > 0 else "未知"
                    label = f"众数({fill_val})"
            elif fill_strategy == "mean":
                fill_val = df[col].mean() if df[col].dtype in (np.float64, np.int64, float, int) else df[col].mode()[0] if len(df[col].mode()) > 0 else "未知"
                label = f"均值/众数({round(fill_val, 2) if isinstance(fill_val, (int, float)) else fill_val})"
            elif fill_strategy == "mode":
                mode_vals = df[col].mode()
                fill_val = mode_vals[0] if len(mode_vals) > 0 else "未知"
                label = f"众数({fill_val})"
            else:
                continue
            df.loc[:, col] = df[col].fillna(fill_val)
            actions.append({
                "action": "填充缺失值",
                "column": col,
                "detail": f"{info['count']} 个 ({info['ratio']}%)，用 {label} 填充",
            })
        if fill_strategy == "drop" and missing:
            before = len(df)
            df = df.dropna()
            actions.append({
                "action": "删除含缺失值的行",
                "detail": f"删除 {before - len(df)} 行",
            })

    # 4. 重复值处理
    dup = detect_duplicates(df)
    if dup["duplicate_rows"] > 0 and remove_duplicates:
        before = len(df)
        df = df.drop_duplicates()
        actions.append({
            "action": "删除重复行",
            "detail": f"删除 {before - len(df)} 行 ({dup['ratio']}%)",
        })

    # 5. 异常值处理（截尾）
    if handle_outliers:
        outliers = detect_outliers(df, method=outlier_method)
        for col, info in outliers.items():
            lower = info["lower_bound"]
            upper = info["upper_bound"]
            df[col] = df[col].clip(lower=lower, upper=upper)
        if outliers:
            total_out = sum(o["count"] for o in outliers.values())
            n_cols = len(outliers)
            actions.append({
                "action": "异常值截尾",
                "detail": f"{n_cols} 个列共 {total_out} 个异常值已裁剪至 [Q1-1.5*IQR, Q3+1.5*IQR]",
            })

    return df, actions


def generate_report(raw_df, cleaned_df, actions, missing_before, dup_before, outliers_before):
    """生成清洗报告（纯文本和 Markdown 格式）"""
    n_rows_before, n_cols_before = raw_df.shape
    n_rows_after, n_cols_after = cleaned_df.shape
    rows_removed = n_rows_before - n_rows_after

    lines = []
    lines.append("# 数据清洗报告")
    lines.append("")

    lines.append("## 基本信息")
    lines.append(f"- 清洗前行数：{n_rows_before}，列数：{n_cols_before}")
    lines.append(f"- 清洗后行数：{n_rows_after}，列数：{n_cols_after}")
    if rows_removed > 0:
        lines.append(f"- 共移除 {rows_removed} 行")
    lines.append("")

    lines.append("## 检测结果")
    # 缺失值
    if missing_before:
        lines.append(f"### 缺失值（{sum(m['count'] for m in missing_before.values())} 个）")
        lines.append("| 列名 | 缺失数 | 占比 |")
        lines.append("|------|--------|------|")
        for col, info in missing_before.items():
            lines.append(f"| {col} | {info['count']} | {info['ratio']}% |")
        lines.append("")
    else:
        lines.append("### 缺失值：未检测到")
        lines.append("")

    # 重复值
    if dup_before.get("duplicate_rows", 0) > 0:
        lines.append(f"### 重复行：{dup_before['duplicate_rows']} 行 ({dup_before['ratio']}%)")
        lines.append("")

    # 异常值
    if outliers_before:
        lines.append(f"### 异常值（{sum(o['count'] for o in outliers_before.values())} 个）")
        lines.append("| 列名 | 异常数 | 占比 | 下界 | 上界 |")
        lines.append("|------|--------|------|------|------|")
        for col, info in outliers_before.items():
            lines.append(f"| {col} | {info['count']} | {info['ratio']}% | {info['lower_bound']} | {info['upper_bound']} |")
        lines.append("")
    else:
        lines.append("### 异常值：未检测到")
        lines.append("")

    # 格式问题
    fmt_issues = detect_format_issues(raw_df)
    if fmt_issues:
        lines.append(f"### 格式问题（{len(fmt_issues)} 项）")
        for issue in fmt_issues:
            lines.append(f"- {issue['column']}：{issue['issue']}" + (f" ({issue.get('count', 0)} 个)" if "count" in issue else ""))
        lines.append("")

    # 执行的操作
    lines.append("## 执行的操作")
    if actions:
        for i, act in enumerate(actions, 1):
            lines.append(f"{i}. **{act['action']}**" + (f" — {act.get('column', '')}" if 'column' in act else ""))
            lines.append(f"   {act['detail']}")
    else:
        lines.append("数据质量良好，无需清洗。")
    lines.append("")

    return "\n".join(lines)


def run_cleaning_pipeline(df, options=None):
    """
    一键清洗流水线：检测 → 清洗 → 报告。

    options 可覆盖 clean_dataframe 的默认参数。
    返回 (cleaned_df, report_markdown)
    """
    opts = {
        "fill_missing": True,
        "fill_strategy": "auto",
        "remove_duplicates": True,
        "handle_outliers": True,
        "outlier_method": "iqr",
        "trim_whitespace": True,
        "clean_column_names": True,
    }
    if options:
        opts.update(options)

    # 清洗前检测
    missing_before = detect_missing(df)
    dup_before = detect_duplicates(df)
    outliers_before = detect_outliers(df, method=opts["outlier_method"])

    # 执行清洗
    cleaned_df, actions = clean_dataframe(df, **opts)

    # 生成报告
    report = generate_report(df, cleaned_df, actions, missing_before, dup_before, outliers_before)

    return cleaned_df, report
