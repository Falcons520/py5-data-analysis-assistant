# AI 数据分析助手

[![CI](https://github.com/Falcons520/py5-data-analysis-assistant/actions/workflows/ci.yml/badge.svg)](https://github.com/Falcons520/py5-data-analysis-assistant/actions/workflows/ci.yml)
[![Docker](https://github.com/Falcons520/py5-data-analysis-assistant/actions/workflows/docker.yml/badge.svg)](https://github.com/Falcons520/py5-data-analysis-assistant/actions/workflows/docker.yml)

上传数据 → 自动清洗 → DeepSeek 智能分析 → 一键导出 **Markdown / Word / Excel / 文本摘要**。

基于 **FastAPI + 原生前端** 的 Web 应用，可直接通过 GitHub 部署到任意容器平台（Render / Railway / 自有服务器 / 群晖 NAS 等）。项目已从 Streamlit 迁移，不再依赖 `streamlit run`。

---

## 功能特性

- **多格式数据接入**：CSV、TSV、TXT、JSON、Excel（`.xlsx` / `.xls` / `.xlsm`），单文件 ≤ 25MB
- **自动数据清洗**：缺失值（均值 / 众数 / 删除）、重复行、异常值（IQR / Z-Score 截尾）、列名规范化、空白修剪，并输出 Markdown 清洗报告
- **AI 分析**：基于 LangChain + DeepSeek 的 Pandas Agent，自动计算指标、生成柱状图 / 折线图 / 散点图并给出业务解读
- **多格式报告导出**：Markdown、Word（含图表嵌入）、Excel（清洗数据 + 统计 + 清洗记录）、100 字核心摘要
- **邮件推送**：通过 SMTP 授权码把报告（含图表附件）发送到指定邮箱
- **任务化执行**：分析任务在后台线程运行，前端轮询进度，不会因请求超时而中断；24 小时后自动清理上传数据与产物

---

## 技术栈

| 层 | 选型 |
| --- | --- |
| Web 框架 | FastAPI + Uvicorn |
| 前端 | 原生 HTML / CSS / JavaScript（无构建步骤） |
| 数据分析 | pandas、numpy、matplotlib |
| 大模型 | LangChain + DeepSeek（`deepseek-chat`） |
| 文档导出 | python-docx、openpyxl |
| 部署 | Docker、GitHub Actions、Render |

---

## 本地运行

```bash
# 1. 创建虚拟环境
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置密钥
set DEEPSEEK_API_KEY=sk-xxxx        # Windows PowerShell: $env:DEEPSEEK_API_KEY="sk-xxxx"
# 或复制 .env.example 为 .env，并自行加载

# 4. 启动
uvicorn server.main:app --reload --port 8000
```

打开 <http://127.0.0.1:8000> 即可使用；接口文档在 <http://127.0.0.1:8000/api/docs>。

---

## 通过 GitHub 上线

仓库地址：<https://github.com/Falcons520/py5-data-analysis-assistant>（已推送 v2.0.0，CI 与镜像构建均为绿色）

仓库已包含部署所需文件：

```
Dockerfile                 生产镜像（含中文字体）
render.yaml                Render 一键部署配置
.github/workflows/ci.yml   测试 + 语法检查
.github/workflows/docker.yml  构建并推送 GHCR 镜像
```

### 方式一：Render（推荐，免费额度即可）

1. 把代码推到 GitHub 仓库（如 `Falcons520/py5-data-analysis-assistant`）。
2. 登录 [Render](https://render.com) → **New → Blueprint** → 选择该仓库，Render 会自动读取 `render.yaml`。
3. 在环境变量里填写 `DEEPSEEK_API_KEY`（勾选 Secret）。
4. 点击 **Apply**，等待构建完成，即可获得 `https://<service>.onrender.com` 地址。

> 免费实例无持久磁盘，重启后上传数据会丢失（任务结果本来也只保留 24 小时）；如需保留，升级套餐并在 `render.yaml` 中挂载磁盘到 `/app/data`。

### 方式二：任意支持 Docker 的平台

```bash
docker build -t ai-data-analysis-assistant .
docker run -d -p 8000:8000 \
  -e DEEPSEEK_API_KEY=sk-xxxx \
  -v $(pwd)/data:/app/data \
  --name analysis-assistant \
  ai-data-analysis-assistant
```

也可以用 GitHub Actions 构建的镜像：

```bash
docker pull ghcr.io/falcons520/py5-data-analysis-assistant:latest
docker run -d -p 8000:8000 -e DEEPSEEK_API_KEY=sk-xxxx ghcr.io/falcons520/py5-data-analysis-assistant:latest
```

### 方式三：自有服务器 / NAS

1. `git clone` 仓库并进入目录。
2. `docker compose up -d --build`（或按上面的 `docker run` 手动启动）。
3. 用 Nginx / Caddy 反向代理到 `8000` 端口，并配置 HTTPS。

---

## 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DEEPSEEK_API_KEY` | 空 | **必填**，DeepSeek API Key |
| `DEEPSEEK_MODEL` | `deepseek-chat` | 模型名（仅用于展示/扩展） |
| `DATA_DIR` | `./data` | 上传文件、图表、报告目录 |
| `MAX_UPLOAD_MB` | `25` | 单文件大小上限 |
| `MAX_CONCURRENT_JOBS` | `2` | 同时运行的分析任务数 |
| `JOB_RETENTION_HOURS` | `24` | 数据集与任务保留时长 |
| `ALLOWED_ORIGINS` | `*` | 允许跨域的来源，逗号分隔 |
| `EMAIL_ENABLED` | `1` | 设为 `0` 关闭邮件功能 |

---

## API 一览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 健康检查（含密钥是否配置） |
| POST | `/api/datasets` | 上传并解析数据文件（multipart） |
| POST | `/api/datasets/demo` | 载入仓库自带的示例数据 |
| GET | `/api/datasets/{id}` | 数据集信息 |
| POST | `/api/datasets/{id}/clean` | 执行数据清洗 |
| POST | `/api/jobs` | 创建分析任务 |
| GET | `/api/jobs/{id}` | 查询任务进度与结果 |
| GET | `/api/jobs/{id}/chart/{file}` | 获取分析图表 |
| GET | `/api/jobs/{id}/download/{kind}` | 下载 `markdown` / `word` / `excel` / `summary` |
| POST | `/api/jobs/{id}/email` | 邮件推送报告 |

---

## 目录结构

```
.
├── server/
│   ├── main.py          FastAPI 路由与静态资源挂载
│   ├── pipeline.py      文件解析 → 清洗 → AI 分析 → 报告生成
│   ├── store.py         数据集 / 任务的文件存储层
│   ├── security.py      HTML 清洗、文件名安全处理
│   └── config.py        环境变量配置
├── static/
│   ├── index.html       单页前端
│   └── assets/          styles.css / app.js
├── L15.py               Pandas Agent、绘图、报告与邮件发送
├── data_cleaning.py     数据清洗流水线
├── report_generator.py  Markdown / Word / Excel / 摘要生成
├── tests/               pytest 接口测试（Mock 大模型）
├── Dockerfile
├── render.yaml
└── .github/workflows/   CI 与镜像构建
```

---

## 测试

```bash
pip install -r requirements-dev.txt
pytest -q
```

测试会替换真实大模型调用，不需要 API Key 与网络。

---

## 安全与限制

- `DEEPSEEK_API_KEY` 只保存在服务端，前端与浏览器均不接触密钥。
- 报告 HTML 经过服务端清洗（移除 `script` / `iframe` / 事件属性 / `javascript:` 链接），前端渲染前再用 `DOMParser` 二次清洗。
- 邮箱授权码只在单次请求内转发给 SMTP 服务器，不写入磁盘、不写日志。
- ⚠️ Pandas Agent 会执行模型生成的 Python 代码（`allow_dangerous_code=True`）。**不要部署成完全公开、无鉴权的服务**；生产环境建议加登录鉴权 / 内网访问 / 限流。
- 分析任务运行在进程内线程中，服务重启会中断进行中的任务；多副本部署时请把任务队列替换为 Celery / RQ 等外部队列。

## 从 Streamlit 迁移的变更

| 旧 | 新 |
| --- | --- |
| `streamlit run app.py` | `uvicorn server.main:app` |
| `.streamlit/secrets.toml` | 环境变量 `DEEPSEEK_API_KEY` |
| `st.session_state` | 数据集 / 任务落盘存储（`data/`） |
| `st.download_button` | `/api/jobs/{id}/download/{kind}` 直链下载 |
| `st.spinner` | 任务进度轮询 + 进度条 |
