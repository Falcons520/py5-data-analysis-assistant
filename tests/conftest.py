import os
from pathlib import Path

# 必须在导入 server 包之前设置，保证测试数据目录隔离。
# 注意：不要用 tempfile.mkdtemp()，在受限沙箱下它创建的目录可能不可写。
_TEST_DATA = Path(__file__).resolve().parent / ".data"
_TEST_DATA.mkdir(parents=True, exist_ok=True)

os.environ.setdefault("DATA_DIR", str(_TEST_DATA))
os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
