# 部署到 Hugging Face Spaces（免费、无需信用卡）

Render 现在创建免费 Web Service 也要求绑定银行卡做身份验证。如果不想绑卡，可以用 Hugging Face Spaces：同样跑 Docker 容器，免费 CPU 2 vCPU / 16 GB，不需要任何支付信息。

## 1. 新建 Space

1. 注册或登录 <https://huggingface.co>
2. 右上头像 → **New Space**
3. 填写：
   - **Space name**：`ai-data-analysis-assistant`
   - **License**：随意（如 MIT）
   - **Select the Space SDK**：**Docker** → **Blank**
   - **Space hardware**：**CPU basic · 2 vCPU · 16 GB · FREE**
   - **Visibility**：Public（免费版只能 Public）
4. 点 **Create Space**

## 2. 上传代码

创建后会得到一个 git 地址：`https://huggingface.co/spaces/<你的用户名>/ai-data-analysis-assistant`

### 方式 A：命令行推送（推荐）

```bash
# 在本地仓库根目录执行
git remote add hf https://huggingface.co/spaces/<你的用户名>/ai-data-analysis-assistant
git push hf master:main
```

首次推送提示输入用户名和密码时：

- 用户名 = Hugging Face 用户名
- 密码 = **Access Token**（头像 → Settings → Access Tokens → New token，勾选 **Write**）

### 方式 B：网页上传

Space 页面 → **Files** → **Add file** → **Upload files**，把仓库内容（`server/`、`static/`、`Dockerfile`、`requirements.txt`、`L15.py`、`data_cleaning.py`、`report_generator.py`、`lesson_data.csv`）拖进去提交。

## 3. 修改 Space 的 README 头部

Hugging Face 通过 README 顶部的 YAML 头识别运行时和端口。把 **Space 里的 README.md** 开头改成：

```yaml
---
title: AI Data Analysis Assistant
emoji: 📊
colorFrom: indigo
colorTo: blue
sdk: docker
app_port: 8000
pinned: false
---

（这里接原本 README 的正文）
```

> 我们的 `Dockerfile` 监听 `${PORT:-8000}`，所以 `app_port: 8000` 与之匹配。不要把端口改成 7860，那需要同时改 Dockerfile。

## 4. 配置密钥

Space 页面 → **Settings** → **Variables and secrets** → **New secret**：

| 名称 | 值 |
| --- | --- |
| `DEEPSEEK_API_KEY` | `sk-...` |
| `ACCESS_TOKEN` | 你的访问口令 |

保存后 Space 会自动重启并使用新密钥。

## 5. 访问

地址形如：`https://<你的用户名>-ai-data-analysis-assistant.hf.space`

- 首次构建约 5–10 分钟（装中文字体 + Python 依赖）
- 构建日志在 Space 页面 **Logs** 标签
- 免费 Space 连续 48 小时无人访问会休眠，唤醒后第一个请求约 30–60 秒

## 已知限制

- 公开 Space 的代码对所有人可见（本仓库本来就是 public，不额外暴露信息）
- 磁盘非持久：容器重启后 `data/` 清空，报告请及时下载
- 免费 CPU 上单次分析 1–3 分钟，`MAX_CONCURRENT_JOBS=2` 之外的请求会返回 429
- 不支持自定义域名（免费版）

## 与 Render 的对比

| | Hugging Face Spaces | Render |
| --- | --- | --- |
| 信用卡 | 不需要 | 免费实例也需绑卡验证 |
| 免费资源 | 2 vCPU / 16 GB | 512 MB 内存 |
| 冷启动 | 48 小时闲置后休眠 | 15 分钟闲置后休眠 |
| 自定义域名 | 免费版不支持 | 支持 |
| 私有服务 | 免费版只能 Public | 可设 Private |
