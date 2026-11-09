"""运行配置：全部通过环境变量控制，便于容器化部署。"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# 本地开发时自动读取项目根目录的 .env（容器/线上直接注入环境变量即可）
try:
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env")
except ImportError:  # 未安装 python-dotenv 时不影响启动
    pass

# 运行期数据目录（上传文件、图表、报告），部署时挂载持久卷即可
DATA_DIR = Path(os.environ.get("DATA_DIR") or (BASE_DIR / "data")).resolve()
STATIC_DIR = BASE_DIR / "static"

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "").strip()
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat").strip()

MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "25"))
MAX_CONCURRENT_JOBS = int(os.environ.get("MAX_CONCURRENT_JOBS", "2"))
JOB_RETENTION_HOURS = int(os.environ.get("JOB_RETENTION_HOURS", "24"))

ALLOWED_ORIGINS = [
    item.strip()
    for item in os.environ.get("ALLOWED_ORIGINS", "*").split(",")
    if item.strip()
]

EMAIL_ENABLED = os.environ.get("EMAIL_ENABLED", "1") not in ("0", "false", "False")
