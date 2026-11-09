"""
报告生成模块：生成 Markdown / Word / Excel / 文本摘要 四种标准化输出。
"""

import io
import os
import re
import json
import pandas as pd
from datetime import datetime


def _build_llm(api_key="", **kwargs):
    """按需构建 DeepSeek 模型客户端（延迟导入，便于服务端启动）"""
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(
        api_key=api_key,
        model="deepseek-chat",
        base_url="https://api.deepseek.com",
        **kwargs,
    )


SUMMARY_PROMPT = """你是一个数据分析报告摘要专家。根据用户输入的分析结果JSON，生成一段**不超过100字**的中文核心结论摘要，用于邮件推送正文。

要求：
- 必须包含最关键的1-2个具体数字
- 点出核心趋势或问题，语言简洁有力
- 严格不超过100字（含标点）
- 仅返回摘要文本，不要任何额外解释、标记或JSON包装"""


def generate_short_summary(analysis_log, api_key=""):
    """调用LLM生成 ≤100 字的核心结论摘要"""
    from langchain_core.prompts import ChatPromptTemplate

    llm = _build_llm(api_key)
    prompt = ChatPromptTemplate.from_messages([
        ("system", SUMMARY_PROMPT),
        ("user", "分析结果JSON：{json_list}\n请生成不超过100字的核心结论摘要。")
    ])
    pmt = prompt.invoke({"json_list": analysis_log})
    ret = llm.invoke(pmt)
    return ret.content.strip()


def generate_short_summary_stream(analysis_log, api_key=""):
    """流式生成核心结论摘要，逐 token 输出（供 SSE / 终端实时展示使用）"""
    from langchain_core.prompts import ChatPromptTemplate

    llm = _build_llm(api_key, streaming=True)
    prompt = ChatPromptTemplate.from_messages([
        ("system", SUMMARY_PROMPT),
        ("user", "分析结果JSON：{json_list}\n请生成不超过100字的核心结论摘要。")
    ])
    pmt = prompt.invoke({"json_list": analysis_log})
    for chunk in llm.stream(pmt):
        if chunk.content:
            yield chunk.content


def build_markdown(report_data, answer, cleaning_report=None, user_query=""):
    """完整 Markdown 分析报告"""
    subject = report_data.get("subject", "数据分析报告")
    lines = [
        f"# {subject}",
        f"*生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}*",
        "",
    ]

    # 一、分析需求
    lines.append("## 一、分析需求")
    lines.append(user_query or answer.get("input", "（未指定）"))
    lines.append("")

    # 二、数据概览
    lines.append("## 二、数据概览")
    chart_info = answer.get("data", {})
    lines.append(f"- 图表类型：{chart_info.get('chart_type', '无')}")
    lines.append(f"- 分析标题：{chart_info.get('title', '无')}")
    if answer.get("chart_paths"):
        lines.append(f"- 图表文件：`{answer['chart_paths']}`")
    lines.append("")

    # 三、数据清洗结论
    sec = 3
    if cleaning_report:
        lines.append(f"## {_num_to_cn(sec)}、数据清洗结论")
        lines.append(cleaning_report)
        lines.append("")
        sec += 1

    # 四、分析摘要与图表解读
    summary = answer.get("data", {}).get("summary", "")
    if summary:
        lines.append(f"## {_num_to_cn(sec)}、分析摘要与图表解读")
        lines.append(summary)
        lines.append("")
        if answer.get("chart_paths"):
            lines.append(f"![图表]({answer['chart_paths']})")
            lines.append("")
        sec += 1

    # 五、详细分析
    html = report_data.get("content_html", "")
    if html:
        lines.append(f"## {_num_to_cn(sec)}、详细分析")
        lines.append(_html_to_md(html))
        lines.append("")
        sec += 1

    # 六、业务建议
    lines.append(f"## {_num_to_cn(sec)}、业务建议")
    lines.append(_extract_recommendations(answer, summary))
    lines.append("")

    # 附件清单
    lines.append("## 附件")
    if answer.get("chart_paths"):
        lines.append(f"- 图表：`{answer['chart_paths']}`")
    lines.append("- 清洗后数据：`*_cleaned.xlsx`")
    lines.append("- Word 文档：`*_报告.docx`")

    return "\n".join(lines)


def build_word(report_data, answer, cleaning_report=None, user_query=""):
    """
    Word 结构化文档，返回 BytesIO。
    需要 python-docx。
    """
    from docx import Document
    from docx.shared import Inches, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    doc = Document()

    # 样式设置
    style = doc.styles["Normal"]
    font = style.font
    font.name = "Microsoft YaHei"
    font.size = Pt(11)

    subject = report_data.get("subject", "数据分析报告")

    # 标题
    title = doc.add_heading(subject, level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    doc.add_paragraph(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}")

    # 1. 分析需求
    doc.add_heading("一、分析需求", level=1)
    doc.add_paragraph(user_query or answer.get("input", "（未指定）"))

    # 2. 数据清洗
    sec = 2
    if cleaning_report:
        doc.add_heading(f"{_num_to_cn(sec)}、数据清洗结论", level=1)
        # 清洗报告是 Markdown，去掉标记符号后写入
        clean_text = re.sub(r"[#*`]", "", cleaning_report)
        for line in clean_text.strip().split("\n"):
            line = line.strip()
            if line:
                doc.add_paragraph(line)
        sec += 1

    # 3. 图表解读
    summary = answer.get("data", {}).get("summary", "")
    if summary:
        doc.add_heading(f"{_num_to_cn(sec)}、分析摘要与图表解读", level=1)
        doc.add_paragraph(summary)

        # 嵌入图表
        chart_paths = answer.get("chart_paths", "")
        if chart_paths and os.path.exists(chart_paths):
            try:
                doc.add_picture(chart_paths, width=Inches(5.5))
                last_paragraph = doc.paragraphs[-1]
                last_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            except Exception:
                doc.add_paragraph(f"[图表：{os.path.basename(chart_paths)}]")
        elif chart_paths:
            doc.add_paragraph(f"[图表占位：{chart_paths}]")
        sec += 1

    # 4. 详细分析（HTML → 结构化段落）
    html = report_data.get("content_html", "")
    if html:
        doc.add_heading(f"{_num_to_cn(sec)}、详细分析", level=1)

        # 解析 HTML 中的 h2/h3/p/table
        blocks = _parse_html_blocks(html)
        for block in blocks:
            tag, text = block
            if tag == "h1":
                doc.add_heading(text, level=1)
            elif tag == "h2":
                doc.add_heading(text, level=2)
            elif tag == "h3":
                doc.add_heading(text, level=3)
            elif tag == "p":
                clean = re.sub(r"<[^>]+>", "", text).strip()
                if clean:
                    doc.add_paragraph(clean)
            elif tag == "table":
                _add_table_to_doc(doc, text)
        sec += 1

    # 5. 业务建议
    doc.add_heading(f"{_num_to_cn(sec)}、业务建议", level=1)
    doc.add_paragraph(_extract_recommendations(answer, summary))

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf


def build_excel(analysis_df, cleaning_report=None):
    """
    Excel 附件，返回 BytesIO。
    Sheet 1: 清洗后数据
    Sheet 2: 指标汇总统计
    """
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        # Sheet 1: 数据
        analysis_df.to_excel(writer, sheet_name="清洗后数据", index=False)

        # Sheet 2: 描述统计
        desc = analysis_df.describe(include="all").T
        desc.to_excel(writer, sheet_name="指标汇总统计")

        # Sheet 3: 清洗报告（如果有）
        if cleaning_report:
            report_lines = cleaning_report.strip().split("\n")
            report_df = pd.DataFrame({"清洗报告": report_lines})
            report_df.to_excel(writer, sheet_name="清洗报告", index=False)

    buf.seek(0)
    return buf


def extract_text_summary(report_data, answer):
    """
    从分析结果中提取 ≤100 字的核心结论摘要。
    优先使用 LLM 生成的短摘要，否则从 summary 中截取。
    """
    summary = answer.get("data", {}).get("summary", "")
    if not summary:
        # 从 HTML 中提取纯文本
        html = report_data.get("content_html", "")
        summary = re.sub(r"<[^>]+>", "", html)

    # 取前 100 字，在完整句子处截断
    if len(summary) <= 100:
        return summary.strip()

    truncated = summary[:100]
    # 尝试在最后一个句号/分号处截断
    for punct in ["。", "；", "，", ".", ";", ","]:
        idx = truncated.rfind(punct)
        if idx > 50:
            return truncated[:idx + 1].strip()
    return truncated.strip() + "…"


# ── 内部工具函数 ──

def _html_to_md(html):
    """简单的 HTML→Markdown 转换"""
    text = html
    text = re.sub(r"<h1>(.*?)</h1>", r"# \1\n", text, flags=re.DOTALL)
    text = re.sub(r"<h2>(.*?)</h2>", r"## \1\n", text, flags=re.DOTALL)
    text = re.sub(r"<h3>(.*?)</h3>", r"### \1\n", text, flags=re.DOTALL)
    text = re.sub(r"<p>(.*?)</p>", r"\1\n\n", text, flags=re.DOTALL)
    text = re.sub(r"<tr>(.*?)</tr>", r"\1\n", text, flags=re.DOTALL)
    text = re.sub(r"<th>(.*?)</th>", r"**\1** | ", text, flags=re.DOTALL)
    text = re.sub(r"<td>(.*?)</td>", r"\1 | ", text, flags=re.DOTALL)
    text = re.sub(r"</?t[hb]ody>", "", text)
    text = re.sub(r"</?table>", "", text)
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _parse_html_blocks(html):
    """解析 HTML 为 (tag, content) 块列表"""
    blocks = []
    pattern = re.compile(
        r"<(h[123]|p|table)>(.*?)</\1>", re.DOTALL
    )
    for match in pattern.finditer(html):
        blocks.append((match.group(1), match.group(2).strip()))
    return blocks


def _add_table_to_doc(doc, html_table):
    """向 Word 文档添加表格"""
    rows = re.findall(r"<tr>(.*?)</tr>", html_table, re.DOTALL)
    if not rows:
        return
    # 取第一行判断列数
    first_cells = re.findall(r"<(?:th|td)>(.*?)</(?:th|td)>", rows[0], re.DOTALL)
    n_cols = len(first_cells)

    table = doc.add_table(rows=len(rows), cols=n_cols, style="Light Grid Accent 1")
    for i, row_html in enumerate(rows):
        cells = re.findall(r"<(?:th|td)>(.*?)</(?:th|td)>", row_html, re.DOTALL)
        for j, cell_text in enumerate(cells):
            if j < n_cols:
                clean = re.sub(r"<[^>]+>", "", cell_text).strip()
                table.cell(i, j).text = clean
    doc.add_paragraph("")


def _extract_recommendations(answer, summary):
    """基于分析生成业务建议"""
    data = answer.get("data", {})
    chart_type = data.get("chart_type", "")
    recs = []

    if chart_type == "funnel" or "漏斗" in summary or "转化" in summary:
        recs.append("1. 针对转化率较低的环节，建议深入分析流失原因，优化用户体验流程。")
    if chart_type == "bar" or "柱状" in summary or "对比" in summary:
        recs.append("2. 关注指标波动较大的维度，排查异常原因并及时调整策略。")
    if chart_type == "line" or "趋势" in summary or "时间" in summary:
        recs.append("3. 密切监控趋势变化，提前制定应对方案，把握增长窗口期。")
    if not recs:
        recs = [
            "1. 建议定期追踪核心指标变化趋势，建立预警机制。",
            "2. 结合业务场景深挖数据背后的驱动因素，制定可落地的优化方案。",
            "3. 持续积累数据资产，为后续深度分析和建模奠定基础。",
        ]
    return "\n".join(recs)


def _num_to_cn(n):
    """数字转中文序号"""
    mapping = {1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六", 7: "七", 8: "八"}
    return mapping.get(n, str(n))
