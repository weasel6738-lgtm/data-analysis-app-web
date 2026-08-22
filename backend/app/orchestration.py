"""Workflow service for manufacturing engineering decisions."""

from __future__ import annotations

import json
from typing import Any

from .config import Settings
from .integrations import IntegrationError, run_copilot_draft, run_microsoft_agent

WORKFLOW_TITLES = {
    "yield-trend": "수율·추세 분석",
    "issue-triage": "공정 이슈 트리아지",
    "spc-fdc": "SPC/FDC 신호 해석",
    "root-cause": "불량 원인 조사",
    "report": "대책·보고서 초안",
}


def _local_workflow(kind: str, context: dict[str, Any], question: str) -> dict[str, Any]:
    manufacturing = context.get("manufacturing", {})
    spc = manufacturing.get("spc") or {}
    correlations = manufacturing.get("correlations") or []
    signals = manufacturing.get("signals") or []
    lead_factor = correlations[0] if correlations else None
    signal_title = signals[0]["title"] if signals else "뚜렷한 이상 신호 없음"
    measure = spc.get("column", "주요 측정값")

    if kind == "yield-trend":
        summary = (
            f"{measure} 중심선은 {spc.get('center', '—')}, 추세는 "
            f"{spc.get('trend', '판단 불가')}입니다."
        )
        steps = ["기간·제품·설비별 층별화", "관리한계 이탈 Lot 원데이터 확인", "변경점 전후 평균 비교"]
    elif kind == "issue-triage":
        summary = f"현재 우선 신호는 ‘{signal_title}’입니다. 영향 범위와 재현성을 먼저 분리합니다."
        steps = ["영향 Lot 홀드 여부 판단", "동일 설비·레시피 공통점 확인", "계측·샘플링 오류 배제"]
    elif kind == "spc-fdc":
        summary = (
            f"{measure}의 3σ 범위는 {spc.get('lcl', '—')}~{spc.get('ucl', '—')}이며 "
            f"이탈 {len(spc.get('violations', []))}건입니다."
        )
        steps = ["Raw trace와 집계 신호 대조", "Run rule 및 센서 건전성 확인", "알람 임계치 재검토"]
    elif kind == "root-cause":
        factor = lead_factor["factor"] if lead_factor else "설비·레시피·계측 조건"
        correlation = lead_factor["correlation"] if lead_factor else "미산출"
        summary = f"우선 조사 후보는 {factor}(상관 {correlation})입니다. 상관은 인과가 아니므로 분할 검증이 필요합니다."
        steps = ["4M1E 변경점 타임라인 작성", "후보 인자별 층별화·재현 시험", "정상/이상 Lot 비교로 반증"]
    else:
        summary = "현상–영향–가설–즉시조치–검증계획 순서의 보고서 초안을 준비했습니다."
        steps = ["현상과 데이터 근거 명시", "임시조치 담당·기한 지정", "재발방지 효과 확인 기준 합의"]

    return {
        "title": WORKFLOW_TITLES[kind],
        "summary": summary,
        "observations": [signal.get("detail", "") for signal in signals[:3]]
        or ["업로드 데이터에서 확정 가능한 이상 신호가 없습니다."],
        "hypotheses": [
            f"{lead_factor['factor']} 조건 변화 영향" if lead_factor else "설비·레시피 조건 변화",
            "계측 또는 샘플링 편향",
            "제품/공정 조건 간 교호작용",
        ],
        "nextSteps": steps,
        "question": question,
        "notice": "결과는 의사결정 보조용입니다. 현장 원데이터와 엔지니어 검증이 필요합니다.",
    }


async def run_workflow(
    kind: str, context: dict[str, Any], question: str, settings: Settings
) -> dict[str, Any]:
    baseline = _local_workflow(kind, context, question)
    provider = "local"
    status = "ready"
    provider_notice = "로컬 결정론 엔진으로 실행했습니다."

    if settings.orchestrator_provider == "microsoft-agent":
        prompt = (
            f"워크플로: {WORKFLOW_TITLES[kind]}\n질문: {question}\n"
            f"분석 컨텍스트: {json.dumps(context, ensure_ascii=False)}\n"
            "관찰/가설/검증계획을 구분하여 간결한 한국어 JSON으로 답하세요."
        )
        try:
            baseline["generatedNarrative"] = await run_microsoft_agent(prompt, settings)
            provider = "microsoft-agent-framework"
            provider_notice = "Microsoft Agent Framework가 분석 단계를 오케스트레이션했습니다."
        except IntegrationError as exc:
            status = "fallback"
            provider_notice = str(exc)

    if kind == "report" and settings.draft_provider == "github-copilot":
        prompt = (
            "다음 제조 이슈 분석을 현상/영향/즉시조치/원인 가설/검증계획/재발방지 "
            f"형식의 한국어 보고서로 작성하세요. 추측은 가설로 표시하세요.\n{json.dumps(baseline, ensure_ascii=False)}"
        )
        try:
            baseline["generatedNarrative"] = await run_copilot_draft(prompt, settings)
            provider = f"{provider}+github-copilot-sdk"
            provider_notice = "GitHub Copilot SDK가 보고서 문안을 작성했습니다."
        except IntegrationError as exc:
            status = "fallback"
            provider_notice = str(exc)

    baseline.update({"provider": provider, "status": status, "providerNotice": provider_notice})
    return baseline
