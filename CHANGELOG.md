# 更新日志

## 2026-11-09 — v2.0.0：移除 Streamlit，改为 FastAPI Web 应用

### 破坏性变更
- 不再使用 `streamlit run app.py`，删除 `app.py`、`.streamlit/`、`packages.txt`
- 启动方式改为 `uvicorn server.main:app --port 8000`
- API Key 从 `.streamlit/secrets.toml` 改为环境变量 `DEEPSEEK_API_KEY`

### 新增
- **FastAPI 后端** (`server/`)：数据集上传 / 预览 / 清洗 / 分析任务 / 报告下载 / 邮件推送共 10 个接口，自带 OpenAPI 文档
- **原生单页前端** (`static/`)：三步式流程（上传 → 预览清洗 → 需求输入）、任务进度轮询、结果区（核心结论、图表、报告、清洗记录、四种下载、邮件表单），无构建步骤
- **后台任务与轮询**：分析在线程中执行，前端 1.2s 轮询进度，规避长请求超时；任务与数据集落盘 `data/`，24 小时自动清理
- **安全加固** (`server/security.py`)：报告 HTML 服务端清洗（移除 script/iframe/事件属性/危险协议），前端 DOMParser 二次清洗；上传扩展名与体积校验；下载文件名白名单
- **部署配置**：`Dockerfile`（含中文字体、非 root、健康检查）、`render.yaml`、`docker-compose.yml`、`.dockerignore`
- **CI/CD**：GitHub Actions 跑语法检查与 pytest，并构建推送 GHCR 镜像
- **测试** (`tests/`)：Mock 大模型的接口测试，覆盖上传、清洗、分析、下载、HTML 清洗

### 重构
- `L15.py` / `report_generator.py` 的 langchain、zmail 改为函数内延迟导入，Web 服务无需 LLM 依赖即可启动
- `draw_chart` 支持指定输出目录并按安全标题命名，便于多任务隔离
- 报告生成、清洗流水线抽出为可复用的 `server/pipeline.py`

### 依赖
- 新增 `fastapi`、`uvicorn[standard]`、`python-multipart`
- 移除 `streamlit`

---

## 2026-07-12

### 新增
- **数据清洗模块** (`data_cleaning.py`)：自动检测缺失值、重复值、异常值（IQR / Z-Score）、格式问题，支持均值/众数填充、截尾、去重，输出 Markdown 清洗报告
- **4 种标准化输出** (`report_generator.py`)：
  1. Markdown 完整分析报告（数据概览 → 清洗结论 → 图表解读 → 详细分析 → 业务建议）
  2. Word 结构化文档（分级标题、规范段落、图表嵌入、表格自动转换）
  3. Excel 附件（清洗后数据 / 指标汇总统计 / 清洗报告 三个工作表）
  4. ≤100 字文本摘要（LLM 生成，含关键数字与趋势结论，用于邮件推送）
- 分析完成后 4 列并排下载按钮（Markdown / Word / Excel / 文本摘要）
- `st.form` + `st.text_input` 替代 `st.text_area`：Enter 直接提交，多行需求展开"多行输入"区域

### 修复
- 下载按钮触发 rerun 后分析结果消失 → 所有结果持久化到 `st.session_state`
- `generate_short_summary` 从 `L15.py` 移入 `report_generator.py`，避免 Streamlit 模块缓存导致的导入失败
- API Key 写入 `.streamlit/secrets.toml`

### 依赖
- 新增 `python-docx>=1.0.0`

---

## 2026-07-10 及之前（git 历史汇总）

- `7a1d774` 扩展支持文件类型（.xls / .json / .tsv / .txt），改进中文字体回退
- `dbed2c3` 强制重建 matplotlib 字体缓存，确保中文显示
- `a87d4e3` 修复 Streamlit Cloud 图表中文乱码：安装 Linux 中文字体 wqy-zenhei
- `dbc27c6` 添加 tabulate 依赖修复导入错误
- `545575f` 支持上传 .xlsx Excel 文件
- `6cd4ee3` 添加 Dev Container 配置
- `f6e78e4` 适配 Streamlit Cloud 部署：通过 st.secrets 管理 API 密钥
- `bd9aaf2` AI 数据分析助手初始版本：基于 DeepSeek 的智能数据分析与报告生成工具
