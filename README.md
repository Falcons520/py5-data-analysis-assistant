# AI 数据分析助手

[![CI](https://github.com/Falcons520/py5-data-analysis-assistant/actions/workflows/ci.yml/badge.svg)](https://github.com/Falcons520/py5-data-analysis-assistant/actions/workflows/ci.yml)
[![Docker](https://github.com/Falcons520/py5-data-analysis-assistant/actions/workflows/docker.yml/badge.svg)](https://github.com/Falcons520/py5-data-analysis-assistant/actions/workflows/docker.yml)

上传数据 → 自动清洗 → DeepSeek 智能分析 → 导出 Markdown / Word / Excel / 文本摘要。

## 功能

- **数据接入**：CSV、TSV、TXT、JSON、Excel（`.xlsx` / `.xls` / `.xlsm`），单文件 ≤ 25MB
- **自动清洗**：缺失值（均值 / 众数 / 删除）、重复行、异常值（IQR / Z-Score 截尾）、列名规范化，输出清洗报告
- **AI 分析**：LangChain + DeepSeek 的 Pandas Agent，自动计算指标、生成柱状图 / 折线图 / 散点图并给出解读
- **报告导出**：Markdown、Word（含图表）、Excel（清洗数据 + 统计 + 清洗记录）、100 字摘要
- **邮件推送**：通过 SMTP 授权码发送报告与图表附件
- **后台任务**：分析在线程中运行、前端轮询进度，数据与产物 24 小时后自动清理

## 技术栈

| 层 | 选型 |
| --- | --- |
| Web 框架 | FastAPI + Uvicorn |
| 前端 | 原生 HTML / CSS / JavaScript |
| 数据分析 | pandas、numpy、matplotlib |
| 大模型 | LangChain + DeepSeek（`deepseek-chat`） |
| 文档导出 | python-docx、openpyxl |
| 部署 | Docker、GitHub Actions |

## 快速开始

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # 填写 DEEPSEEK_API_KEY
uvicorn server.main:app --reload --port 8000
```

打开 <http://127.0.0.1:8000>，接口文档在 <http://127.0.0.1:8000/api/docs>。

## 部署

### Docker

```bash
docker build -t ai-data-analysis-assistant .
docker run -d -p 8000:8000 \
  -e DEEPSEEK_API_KEY=sk-xxxx \
  -e ACCESS_TOKEN=your-token \
  -v $(pwd)/data:/app/data \
  ai-data-analysis-assistant
```

或直接 `docker compose up -d --build`（从 `.env` 读取配置）。

### Render

1. **New → Blueprint**，选择本仓库，自动读取 `render.yaml`
2. 填写环境变量 `DEEPSEEK_API_KEY` 与 `ACCESS_TOKEN`
3. **Apply**，构建完成后获得 `https://<service>.onrender.com`

免费实例无持久磁盘，重启后 `data/` 会清空；需要保留请升级套餐并挂载磁盘。

### Hugging Face Spaces

见 [docs/huggingface-space.md](docs/huggingface-space.md)。

## 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DEEPSEEK_API_KEY` | 空 | 必填，DeepSeek API Key |
| `ACCESS_TOKEN` | 空 | 访问口令；设置后除健康检查外所有接口都需携带，留空则不设防 |
| `DEEPSEEK_MODEL` | `deepseek-chat` | 模型名 |
| `DATA_DIR` | `./data` | 上传文件、图表、报告目录 |
| `MAX_UPLOAD_MB` | `25` | 单文件大小上限 |
| `MAX_CONCURRENT_JOBS` | `2` | 同时运行的分析任务数 |
| `JOB_RETENTION_HOURS` | `24` | 数据集与任务保留时长，`0` 关闭清理 |
| `ALLOWED_ORIGINS` | `*` | 允许跨域的来源，逗号分隔 |
| `EMAIL_ENABLED` | `1` | 设为 `0` 关闭邮件功能 |

## API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 健康检查（含密钥是否配置） |
| POST | `/api/datasets` | 上传并解析数据文件（multipart） |
| POST | `/api/datasets/demo` | 载入自带示例数据 |
| GET | `/api/datasets/{id}` | 数据集信息 |
| POST | `/api/datasets/{id}/clean` | 执行数据清洗 |
| POST | `/api/jobs` | 创建分析任务 |
| GET | `/api/jobs/{id}` | 查询任务进度与结果 |
| GET | `/api/jobs/{id}/chart/{file}` | 获取分析图表 |
| GET | `/api/jobs/{id}/download/{kind}` | 下载 `markdown` / `word` / `excel` / `summary` |
| POST | `/api/jobs/{id}/email` | 邮件推送报告 |

## 目录结构

```
server/          FastAPI 路由、分析流水线、存储、安全清洗、配置
static/          单页前端（index.html + assets）
tests/           pytest 接口测试（Mock 大模型）
L15.py           Pandas Agent、绘图、报告与邮件发送
data_cleaning.py 数据清洗流水线
report_generator.py  Markdown / Word / Excel / 摘要生成
```

## 测试

```bash
pip install -r requirements-dev.txt
pytest -q
```

## 安全说明

- `DEEPSEEK_API_KEY` 只保存在服务端，前端不接触密钥。
- 报告 HTML 在服务端清洗（移除 `script` / 事件属性 / `javascript:` 链接），前端渲染前再清洗一次。
- Pandas Agent 会执行模型生成的 Python 代码（`allow_dangerous_code=True`），公开部署请设置 `ACCESS_TOKEN` 或限制在内网。
- 分析任务运行在进程内线程，服务重启会中断进行中的任务；多副本部署需改用 Celery / RQ 等外部队列。
