"""FastAPI entry point for the FabriQ manufacturing technology workbench."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .analysis import analyze_csv
from .config import get_settings
from .demo_data import SYNTHETIC_DEMO_CSV
from .integrations import integration_status
from .models import WorkflowRequest
from .orchestration import run_workflow

settings = get_settings()
logger = logging.getLogger("fabriq.api")
app = FastAPI(
    title=settings.app_name,
    description="양산기술 엔지니어를 위한 제조 데이터 분석·이슈 대응 워크벤치",
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("x-request-id", str(uuid4()))
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("Unhandled API error [request_id=%s]", request_id)
        response = JSONResponse(
            status_code=500,
            content={
                "detail": "서버에서 요청을 처리하지 못했습니다. 요청 ID와 함께 관리자에게 문의하세요.",
                "requestId": request_id,
            },
        )
    response.headers["x-request-id"] = request_id
    response.headers["x-content-type-options"] = "nosniff"
    return response


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": "fabriq-api",
        "environment": settings.environment,
    }


@app.get("/api/config")
def config() -> dict:
    return {
        "appName": settings.app_name,
        "maxUploadMb": settings.max_upload_mb,
        "integrations": integration_status(settings),
    }


@app.get("/api/sample")
@app.get("/api/dashboard")
def sample() -> dict:
    result = analyze_csv(
        SYNTHETIC_DEMO_CSV,
        "synthetic-fab-yield-demo.csv",
        is_synthetic=True,
    ).to_dict()
    result["dataNotice"] = (
        "이 화면의 모든 값과 식별자는 제품 시연용으로 생성한 합성 데이터이며 "
        "SK hynix의 실제·기밀 데이터를 포함하지 않습니다."
    )
    return result


@app.post("/api/analyze")
async def analyze(file: Annotated[UploadFile, File(...)]) -> dict:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail=".csv 파일을 선택하세요.")
    content = await file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"CSV 파일은 {settings.max_upload_mb} MB 이하여야 합니다.",
        )
    try:
        return analyze_csv(content, file.filename).to_dict()
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="CSV는 UTF-8 인코딩이어야 합니다.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/workflows")
async def workflow(request: WorkflowRequest) -> dict:
    return await run_workflow(
        request.kind,
        request.context,
        request.question,
        settings,
    )


frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
