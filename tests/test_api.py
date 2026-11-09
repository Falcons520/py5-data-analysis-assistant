import time

import pytest
from fastapi.testclient import TestClient

from server import main as app_module
from server import pipeline


CSV = "月份,PV,UV\n1月,100,50\n2月,120,60\n3月,90,45\n"


@pytest.fixture(scope="module")
def client():
    with TestClient(app_module.app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def patch_llm(monkeypatch):
    """用假数据替换真实大模型调用，避免测试依赖网络与密钥。"""

    def fake_agent(csv_path, user_query, api_key="", output_dir="artifacts"):
        return {
            "type": "chart_data",
            "input": user_query,
            "data": {
                "chart_type": "bar",
                "x": ["1月", "2月", "3月"],
                "y_series": {"PV": [100, 120, 90]},
                "summary": "测试摘要：PV 在 2 月达到峰值。",
                "title": "测试图表",
                "xlabel": "月份",
                "ylabel": "PV",
            },
            "chart_paths": "",
        }

    def fake_report(analysis_log, api_key=""):
        return {
            "subject": "测试报告",
            "content_html": (
                "<h1>测试报告</h1><p>正文</p>"
                "<script>alert(1)</script>"
                "<table><tbody><tr><th>PV</th><td>310</td></tr></tbody></table>"
            ),
            "attachments": [],
        }

    monkeypatch.setattr(pipeline.L15, "data_analyze_agent", fake_agent)
    monkeypatch.setattr(pipeline.L15, "generate_report", fake_report)
    monkeypatch.setattr(pipeline, "generate_short_summary", lambda log, key="": "测试核心结论：PV 约 310。")


def upload(client):
    response = client.post(
        "/api/datasets",
        files={"file": ("test.csv", CSV.encode("utf-8"), "text/csv")},
    )
    assert response.status_code == 200, response.text
    return response.json()


def wait_job(client, job_id, timeout=15.0):
    deadline = time.time() + timeout
    payload = {}
    while time.time() < deadline:
        payload = client.get(f"/api/jobs/{job_id}").json()
        if payload["status"] in ("succeeded", "failed"):
            return payload
        time.sleep(0.1)
    raise AssertionError(f"任务超时：{payload}")


def test_health(client):
    data = client.get("/api/health").json()
    assert data["status"] == "ok"
    assert data["key_configured"] is True


def test_home_page(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "AI 数据分析助手" in response.text


def test_upload_dataset(client):
    data = upload(client)
    dataset = data["dataset"]
    assert dataset["rows"] == 3
    assert dataset["cols"] == 3
    assert dataset["columns"] == ["月份", "PV", "UV"]
    assert data["preview"][0][1] == 100


def test_reject_unsupported_file(client):
    response = client.post(
        "/api/datasets",
        files={"file": ("bad.exe", b"binary", "application/octet-stream")},
    )
    assert response.status_code == 400


def test_clean_dataset(client):
    dataset_id = upload(client)["dataset"]["id"]
    response = client.post(
        f"/api/datasets/{dataset_id}/clean",
        json={"fill_strategy": "auto", "outlier_method": "iqr", "remove_duplicates": True},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert "# 数据清洗报告" in body["report"]
    assert body["rows"] >= 1
    assert len(body["preview"]) <= 10


def test_full_analysis_and_downloads(client):
    dataset_id = upload(client)["dataset"]["id"]
    response = client.post(
        "/api/jobs",
        json={"dataset_id": dataset_id, "query": "按月汇总 PV 并生成柱状图"},
    )
    assert response.status_code == 200, response.text

    payload = wait_job(client, response.json()["job_id"])
    assert payload["status"] == "succeeded", payload.get("error")
    assert payload["progress"] == 100

    result = payload["result"]
    assert result["short_summary"] == "测试核心结论：PV 约 310。"
    assert "<script>" not in result["report_html"]
    assert "测试报告" in result["report_html"]
    assert set(result["downloads"]) == {"markdown", "word", "excel", "summary"}

    下载 = client.get(result["downloads"]["markdown"])
    assert 下载.status_code == 200
    assert "测试报告" in 下载.text

    assert client.get(result["downloads"]["word"]).status_code == 200
    assert client.get(result["downloads"]["excel"]).status_code == 200


def test_job_not_found(client):
    assert client.get("/api/jobs/not-a-real-id").status_code == 404
