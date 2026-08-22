"""LLM-assisted document classification through Microsoft Agent Framework."""

from __future__ import annotations

import json
from typing import Any, Sequence

from .config import Settings
from .document_organizer import CATEGORIES, ProcessedDocument, extract_text
from .integrations import IntegrationError, run_copilot_draft, run_microsoft_agent


async def _run_ai(prompt: str, settings: Settings) -> str:
    if settings.draft_provider == "github-copilot":
        return await run_copilot_draft(prompt, settings)
    return await run_microsoft_agent(prompt, settings)


def _parse_response(raw: str) -> list[dict[str, Any]]:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    payload = json.loads(cleaned)
    if not isinstance(payload, list):
        raise ValueError("LLM 응답은 JSON 배열이어야 합니다.")
    return [item for item in payload if isinstance(item, dict)]


async def classify_documents_with_agent(
    records: Sequence[ProcessedDocument], settings: Settings
) -> int:
    """Apply validated LLM classifications and return the number changed."""

    documents: list[dict[str, str]] = []
    for record in records:
        extraction = extract_text(record.original_path, record.content)
        documents.append(
            {
                "id": record.document_id,
                "filename": record.original_path,
                "extension": (
                    record.original_path.rsplit(".", 1)[-1].lower()
                    if "." in record.original_path
                    else ""
                ),
                "content": extraction.text[:12000],
            }
        )

    prompt = (
        "문서 분류 전문가로서 아래 문서들을 분류하세요. "
        f"허용 카테고리는 {', '.join(CATEGORIES)} 입니다.\n"
        "파일명, 확장자, 내용을 종합하되 확실하지 않으면 기타/분류불가를 선택하세요. "
        "각 항목에 id, category, confidence(0~1 숫자), reason(한국어 한 문장), "
        "matched_keywords(문자열 배열)을 포함하세요. 반드시 JSON 배열만 답하세요.\n"
        f"문서 목록:\n{json.dumps(documents, ensure_ascii=False)}"
    )
    results = _parse_response(await _run_ai(prompt, settings))
    by_id = {str(item.get("id")): item for item in results}
    changed = 0
    for record in records:
        item = by_id.get(record.document_id)
        category = item.get("category") if item else None
        if category not in CATEGORIES:
            continue
        try:
            confidence = min(1.0, max(0.0, float(item.get("confidence", 0))))
        except (TypeError, ValueError):
            continue
        reason = str(item.get("reason", "LLM이 문서 형식과 내용을 종합해 판단했습니다."))
        keywords = item.get("matched_keywords", [])
        if not isinstance(keywords, list):
            keywords = []
        record.suggested_category = category
        record.confidence = round(confidence, 2)
        record.reason = reason
        record.matched_keywords = tuple(str(keyword) for keyword in keywords[:10])
        record.classification_source = "microsoft-agent"
        changed += 1
    return changed


async def group_documents_with_agent(
    records: Sequence[ProcessedDocument], settings: Settings
) -> int:
    """Discover document groups instead of choosing from a fixed taxonomy."""

    documents = []
    for record in records:
        extraction = extract_text(record.original_path, record.content)
        documents.append(
            {
                "id": record.document_id,
                "filename": record.original_path,
                "content": extraction.text[:12000],
            }
        )
    prompt = (
        "업로드된 논문과 문서의 연구 주제에 따른 의미적 유사성을 비교해 그룹을 발견하세요. "
        "미리 정해진 카테고리 목록을 사용하지 말고, 연구 대상·핵심 문제·방법론을 설명하는 "
        "짧은 한국어 주제 그룹명을 새로 만드세요. 예: 자연어 처리, 의료 영상 분석, "
        "강화학습, 반도체 공정 최적화. 계약서·보고서·논문·강의자료처럼 문서 형식이나 "
        "역할을 그룹명으로 사용하지 마세요. 파일명과 확장자는 보조 정보로만 사용하고 "
        "본문의 연구 주제와 핵심 내용을 최우선으로 판단하세요. "
        "각 문서는 정확히 하나의 그룹에 배정하세요. 반드시 다음 JSON 배열만 답하세요: "
        "[{\"id\":\"문서 id\",\"group\":\"그룹명\","
        "\"confidence\":0.0,\"reason\":\"한국어 근거\","
        "\"matched_keywords\":[\"근거 단어\"]}].\n"
        f"문서 목록:\n{json.dumps(documents, ensure_ascii=False)}"
    )
    results = _parse_response(await _run_ai(prompt, settings))
    by_id = {str(item.get("id")): item for item in results}
    changed = 0
    for record in records:
        item = by_id.get(record.document_id)
        group = str(item.get("group", "")).strip() if item else ""
        if not group or len(group) > 80 or any(char in group for char in "/\\\x00"):
            continue
        try:
            confidence = min(1.0, max(0.0, float(item.get("confidence", 0))))
        except (TypeError, ValueError):
            continue
        keywords = item.get("matched_keywords", [])
        if not isinstance(keywords, list):
            keywords = []
        record.suggested_category = group
        record.confidence = round(confidence, 2)
        record.reason = str(item.get("reason", "파일 간 의미적 유사성을 바탕으로 그룹화했습니다."))
        record.matched_keywords = tuple(str(keyword) for keyword in keywords[:10])
        record.classification_source = "microsoft-agent-semantic"
        changed += 1
    return changed


__all__ = ["IntegrationError", "classify_documents_with_agent", "group_documents_with_agent"]