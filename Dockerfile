# AI 数据分析助手 —— 生产镜像
# 构建：docker build -t ai-data-analysis-assistant .
# 运行：docker run -p 8000:8000 -e DEEPSEEK_API_KEY=sk-xxx ai-data-analysis-assistant

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MPLBACKEND=Agg \
    DATA_DIR=/app/data \
    PORT=8000

WORKDIR /app

# 中文字体：保证 matplotlib 图表中文不乱码
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-wqy-zenhei fonts-noto-cjk curl \
    && rm -rf /var/lib/apt/lists/* \
    && fc-cache -f

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data && useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT}/api/health" || exit 1

CMD ["sh", "-c", "uvicorn server.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips '*'"]
