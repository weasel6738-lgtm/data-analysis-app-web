from fastapi.testclient import TestClient
import asyncio
from dataclasses import replace

try:
    from app import integrations
    from app.analysis import analyze_csv
    from app.config import get_settings
    from app.main import app
    from app.orchestration import run_workflow
except ModuleNotFoundError:
    from backend.app import integrations
    from backend.app.analysis import analyze_csv
    from backend.app.config import get_settings
    from backend.app.main import app
    from backend.app.orchestration import run_workflow


def test_manufacturing_analysis_returns_spc_and_correlations():
    result = analyze_csv(
        "date,yield_pct,pressure\n"
        "2026-01-01,98,40\n2026-01-02,97,42\n2026-01-03,96,44\n"
        "2026-01-04,95,46\n2026-01-05,94,48\n2026-01-06,93,50\n",
        "test.csv",
    )

    assert result.row_count == 6
    assert result.manufacturing["spc"]["column"] == "yield_pct"
    assert result.manufacturing["spc"]["trend"] == "하락"
    assert result.manufacturing["correlations"][0] == {
        "factor": "pressure",
        "correlation": -1.0,
        "direction": "반대로 이동",
    }


def test_sample_endpoint_is_explicitly_synthetic():
    response = TestClient(app).get("/api/dashboard")

    assert response.status_code == 200
    body = response.json()
    assert body["isSynthetic"] is True
    assert "합성 데이터" in body["dataNotice"]
    assert body["manufacturing"]["yieldColumn"] == "yield_pct"


def test_workflow_separates_observation_and_hypothesis():
    client = TestClient(app)
    context = client.get("/api/dashboard").json()
    response = client.post(
        "/api/workflows",
        json={"kind": "root-cause", "context": context, "question": "우선 확인할 것은?"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["observations"]
    assert body["hypotheses"]
    assert "현장" in body["notice"]


def test_upload_rejects_non_csv_and_empty_csv():
    client = TestClient(app)
    non_csv = client.post(
        "/api/analyze", files={"file": ("notes.txt", b"hello", "text/plain")}
    )
    empty = client.post(
        "/api/analyze", files={"file": ("empty.csv", b"", "text/csv")}
    )

    assert non_csv.status_code == 400
    assert empty.status_code == 400
    assert "비어" in empty.json()["detail"]


def test_unknown_workflow_is_validation_error():
    response = TestClient(app).post(
        "/api/workflows", json={"kind": "unknown", "context": {}}
    )
    assert response.status_code == 422


def test_missing_optional_agent_sdk_falls_back_safely(monkeypatch):
    monkeypatch.setattr(integrations.importlib.util, "find_spec", lambda _name: None)
    configured = replace(
        get_settings(),
        orchestrator_provider="microsoft-agent",
        azure_openai_endpoint="https://example.openai.azure.com",
        azure_openai_deployment="demo",
    )
    result = asyncio.run(
        run_workflow("issue-triage", {"manufacturing": {}}, "", configured)
    )

    assert result["status"] == "fallback"
    assert result["provider"] == "local"
    assert "패키지" in result["providerNotice"]
