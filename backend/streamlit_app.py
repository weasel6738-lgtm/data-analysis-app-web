"""Korean Streamlit UI for the offline document organizer."""

from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st
from streamlit.errors import StreamlitAPIException

try:
    from app.document_organizer import (
        CATEGORIES,
        InputDocument,
        create_organized_zip,
        create_organized_folder,
        process_documents,
    )
    from app.config import get_settings
    from app.document_ai import (
        IntegrationError,
        group_documents_with_agent,
    )
    from app.integrations import integration_status
except ModuleNotFoundError:
    from backend.app.document_organizer import (
        CATEGORIES,
        InputDocument,
        create_organized_zip,
        create_organized_folder,
        process_documents,
    )
    from backend.app.config import get_settings
    from backend.app.document_ai import (
        IntegrationError,
        group_documents_with_agent,
    )
    from backend.app.integrations import integration_status


STATUS_LABELS = {
    "ready": "처리 가능",
    "empty": "빈 문서",
    "unsupported": "지원하지 않음",
    "error": "오류",
    "ai-unavailable": "AI 연결 필요",
}


def _render_styles() -> None:
    st.markdown(
        """
        <style>
        :root { --ink: #18232d; --muted: #687581; --line: #d9e0e5; --blue: #1769aa; --paper: #f7f9fa; }
        .block-container { max-width: 1180px; padding-top: 2.5rem; padding-bottom: 4rem; }
        h1 { color: var(--ink); letter-spacing: -0.02em; }
        h2, h3 { color: var(--ink); }
        .app-kicker { color: var(--blue); font-size: 0.78rem; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; }
        .app-subtitle { color: var(--muted); margin-top: -0.6rem; }
        .step-card { background: var(--paper); border: 1px solid var(--line); border-radius: 8px; padding: 0.8rem 1rem; min-height: 5.3rem; }
        .step-card.active { border-color: var(--blue); box-shadow: 0 0 0 1px var(--blue) inset; }
        .step-number { color: var(--blue); font-size: 0.74rem; font-weight: 700; }
        .step-name { color: var(--ink); font-weight: 700; margin-top: 0.25rem; }
        .step-state { color: var(--muted); font-size: 0.78rem; margin-top: 0.25rem; }
        .upload-note { background: #eef6fc; border-left: 4px solid var(--blue); padding: 0.8rem 1rem; color: var(--ink); }
        [data-testid="stFileUploader"] { border: 1px dashed #9bb4c8; border-radius: 8px; padding: 0.4rem; background: #fbfdff; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_steps(stage: int) -> None:
    steps = [(1, "파일 업로드"), (2, "AI 자동 분석"), (3, "분류안 검토"), (4, "결과 내보내기")]
    columns = st.columns(4)
    for column, (number, name) in zip(columns, steps):
        state = "완료" if number < stage else "진행 중" if number == stage else "대기"
        with column:
            st.markdown(
                f'<div class="step-card {"active" if number == stage else ""}">'
                f'<div class="step-number">STEP {number}</div>'
                f'<div class="step-name">{name}</div>'
                f'<div class="step-state">{state}</div></div>',
                unsafe_allow_html=True,
            )


def _upload_widget() -> tuple[list[Any], bool]:
    supported_types = [
        "txt", "md", "csv", "xlsx", "docx", "pdf",
        "bmp", "gif", "jpeg", "jpg", "png", "tif", "tiff", "webp",
    ]
    try:
        files = st.file_uploader(
            "정리할 폴더를 선택하세요",
            accept_multiple_files="directory",
            type=supported_types,
            key="directory_upload",
            help="폴더 안의 파일을 여러 개 불러옵니다. 브라우저에 따라 상대 경로가 보존됩니다.",
        )
        return list(files or []), True
    except (TypeError, StreamlitAPIException):
        files = st.file_uploader(
            "정리할 파일을 여러 개 선택하세요",
            accept_multiple_files=True,
            type=supported_types,
            key="multiple_upload",
            help="현재 Streamlit 버전에서는 폴더 선택을 지원하지 않아 여러 파일 선택으로 동작합니다.",
        )
        return list(files or []), False


def _keyword_editor() -> dict[str, tuple[str, ...]]:
    with st.expander("분류 키워드 설정", expanded=False):
        st.caption("쉼표로 구분해 수정할 수 있습니다. 본문 내용이 파일명보다 높은 우선순위를 가집니다.")
        st.markdown("#### 내가 정하는 분류 기준")
        st.caption("분류명과 본문에서 찾을 단어를 직접 입력하세요. 파일명과 확장자는 분류 기준으로 사용하지 않습니다.")
        st.caption("한 행이 하나의 분류이며, 키워드는 쉼표로 구분합니다. 예: 학생 자료 | 강의, 수강생, 학번")
        edited = st.data_editor(
            [{"분류명": "", "본문 키워드(쉼표 구분)": ""}],
            num_rows="dynamic",
            hide_index=True,
            use_container_width=True,
            column_config={
                "분류명": st.column_config.TextColumn("분류명", required=True),
                "본문 키워드(쉼표 구분)": st.column_config.TextColumn(
                    "본문 키워드(쉼표 구분)", required=True
                ),
            },
            key="custom_classification_rules",
        )
        configured: dict[str, tuple[str, ...]] = {}
        for row in _edited_rows(edited):
            category = str(row.get("분류명", "")).strip()
            keywords = tuple(
                keyword.strip()
                for keyword in str(row.get("본문 키워드(쉼표 구분)", "")).split(",")
                if keyword.strip()
            )
            if category and keywords:
                configured[category] = keywords
        if not configured:
            st.warning("분류를 시작하려면 분류명과 본문 키워드를 한 개 이상 입력하세요.")
        return configured
    return configured


def _classification_guide() -> None:
    with st.expander("분류 기준과 점수 계산 방식", expanded=True):
        st.markdown(
            """
            **자동 분류는 다음 순서로 진행됩니다.**

            - 사용자가 입력한 분류명과 본문 키워드만 분류 기준으로 사용합니다.
            - 읽을 수 있는 문서의 내용에서 키워드를 찾습니다. 내용 일치는 키워드마다 **4점**입니다.
            - 파일명과 확장자는 분류 기준에 포함하지 않습니다.
            - 가장 높은 점수의 분류를 추천하고, 점수 차이를 바탕으로 신뢰도를 계산합니다.
            - 일치 키워드가 없으면 `기타/분류불가`로 처리합니다.

            최종 분류는 자동 추천이며, 검토 단계에서 직접 바꿀 수 있습니다. 본문을 읽을 수 없는
            파일은 사용자 키워드와 비교할 수 없으므로 처리 상태와 오류를 함께 표시합니다.
            손상·암호화·미지원 파일은 원본을 보존하되
            처리 상태와 오류를 함께 표시합니다.
            """
        )


def _classification_summary(records: list[Any]) -> None:
    counts: dict[str, int] = {}
    for record in records:
        counts[record.suggested_category] = counts.get(record.suggested_category, 0) + 1
    st.markdown("#### AI 주제 그룹 결과 요약")
    columns = st.columns(min(max(len(counts), 1), 4))
    for column, (category, count) in zip(columns, sorted(counts.items())):
        with column:
            st.metric(category, f"{count}개")

    with st.expander("파일별 주제 그룹과 근거 보기", expanded=True):
        for record in records:
            evidence = record.reason or "일치하는 키워드가 없습니다."
            keywords = ", ".join(record.matched_keywords) or "없음"
            status = STATUS_LABELS.get(record.processing_status, record.processing_status)
            source = (
                "Microsoft Agent Framework · 의미 그룹화"
                if record.classification_source == "microsoft-agent-semantic"
                else "Microsoft Agent Framework"
                if record.classification_source == "microsoft-agent"
                else "AI 분석 미실행"
                if record.classification_source == "ai-unavailable"
                else "로컬 규칙 엔진"
            )
            st.markdown(
                f"**{record.original_name}** → `{record.suggested_category}` "
                f"(신뢰도 {record.confidence:.2f}, 상태: {status}, 방식: {source})"
            )
            st.caption(f"근거: {evidence} · 일치 키워드: {keywords}")


def _ai_connection_message() -> tuple[str, bool]:
    settings = get_settings()
    status = integration_status(settings)
    if settings.draft_provider == "github-copilot":
        configured = status["drafting"]["sdkInstalled"] and status["drafting"]["configured"]
        return (
            "GitHub Copilot SDK"
            if configured
            else "GitHub Copilot SDK가 설치되지 않았거나 GITHUB_TOKEN이 없습니다.",
            configured,
        )
    if settings.orchestrator_provider == "microsoft-agent":
        configured = status["orchestrator"]["sdkInstalled"] and status["orchestrator"]["configured"]
        return (
            "Microsoft Agent Framework"
            if configured
            else "Microsoft Agent Framework, AZURE_OPENAI_ENDPOINT 또는 AZURE_OPENAI_DEPLOYMENT 설정이 없습니다.",
            configured,
        )
    return "AI 제공자가 선택되지 않았습니다. DRAFT_PROVIDER=github-copilot을 설정하세요.", False


def _render_ai_status() -> tuple[str, bool]:
    settings = get_settings()
    status = integration_status(settings)
    if settings.draft_provider == "github-copilot":
        sdk_ready = status["drafting"]["sdkInstalled"]
        token_ready = status["drafting"]["configured"]
        provider = "GitHub Copilot SDK"
    elif settings.orchestrator_provider == "microsoft-agent":
        sdk_ready = status["orchestrator"]["sdkInstalled"]
        token_ready = status["orchestrator"]["configured"]
        provider = "Microsoft Agent Framework + Azure OpenAI"
    else:
        sdk_ready = False
        token_ready = False
        provider = "AI 제공자 미선택"
    ready = sdk_ready and token_ready
    with st.container(border=True):
        st.markdown("#### AI 연결 상태")
        columns = st.columns(3)
        columns[0].metric("AI 제공자", provider)
        columns[1].metric("SDK", "연결됨" if sdk_ready else "없음")
        columns[2].metric("인증 토큰", "확인됨" if token_ready else "없음")
        if ready:
            st.success("AI 분석을 실행할 수 있습니다.")
        else:
            st.error("인증 토큰이 없거나 AI 설정이 완료되지 않아 문서 분석을 실행할 수 없습니다.")
            st.caption("토큰 값은 화면에 표시하지 않습니다. 서버 환경변수 GITHUB_TOKEN을 설정한 뒤 서버를 재시작하세요.")
    return provider, ready


def _rows(records: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "ID": record.document_id,
            "원본 경로": record.original_path,
            "파일명": record.original_name,
            "처리 상태": STATUS_LABELS.get(record.processing_status, record.processing_status),
            "추천 분류": record.suggested_category,
            "분류 방식": "LLM 의미 그룹화"
            if record.classification_source == "microsoft-agent-semantic"
            else "LLM"
            if record.classification_source == "microsoft-agent"
            else "AI 분석 미실행"
            if record.classification_source == "ai-unavailable"
            else "로컬 규칙",
            "최종 분류": record.suggested_category,
            "신뢰도": record.confidence,
            "분류 근거": record.reason,
            "오류": record.error,
            "참고": record.note,
        }
        for record in records
    ]


def _edited_rows(editor_value: Any) -> list[dict[str, Any]]:
    if hasattr(editor_value, "to_dict"):
        return editor_value.to_dict(orient="records")
    return list(editor_value)


def _upload_signature(uploaded_files: list[Any]) -> str:
    digest = hashlib.sha256()
    for uploaded in uploaded_files:
        digest.update(uploaded.name.encode("utf-8", errors="replace"))
        digest.update(uploaded.getvalue())
    return digest.hexdigest()


def main() -> None:
    st.set_page_config(page_title="문서 자동 분류", page_icon="🗂️", layout="wide")
    _render_styles()
    st.markdown('<div class="app-kicker">OFFLINE DOCUMENT WORKBENCH</div>', unsafe_allow_html=True)
    st.title("문서 자동 분류 도우미")
    st.markdown('<p class="app-subtitle">파일을 올리고, 분류를 확인한 뒤 안전하게 결과를 내보내세요.</p>', unsafe_allow_html=True)
    st.info(
        "브라우저 업로드는 원본 폴더의 **복사본**만 읽습니다. "
        "원본 파일을 이동·수정·삭제하지 않으며, 확인 후 분류별 폴더 또는 새 ZIP을 생성합니다."
    )

    records = st.session_state.get("document_records")
    _render_steps(3 if records else 1)
    _, ai_ready = _render_ai_status()
    st.subheader("파일 업로드")
    st.caption("논문이나 문서를 올리면 AI가 본문의 연구 주제를 파악하고 유사한 주제끼리 묶습니다.")
    uploaded_files, folder_supported = _upload_widget()
    if not folder_supported:
        st.caption("폴더 경로 대신 파일명만 보존될 수 있습니다.")
    if uploaded_files:
        st.success(f"{len(uploaded_files)}개 파일이 선택되었습니다.")
        with st.expander("선택한 파일 확인", expanded=False):
            st.write("\n".join(uploaded.name for uploaded in uploaded_files))

    if uploaded_files and not ai_ready:
        st.error("파일은 업로드되었지만 인증 토큰이 없어 AI 분석을 시작할 수 없습니다.")
    upload_signature = _upload_signature(uploaded_files) if uploaded_files else ""
    should_analyze = bool(uploaded_files and ai_ready and upload_signature != st.session_state.get("analyzed_upload_signature"))
    if should_analyze:
        inputs = [
            InputDocument(path=uploaded.name, content=uploaded.getvalue())
            for uploaded in uploaded_files
        ]
        progress = st.progress(0, text="분류 준비 중... 0%")
        settings = get_settings()
        if ai_ready:
            try:
                provider = "GitHub Copilot" if settings.draft_provider == "github-copilot" else "Microsoft Agent Framework"
                with st.spinner(f"{provider}가 문서 본문을 읽고 주제를 분석하고 있습니다..."):
                    progress.progress(0.2, text="문서 내용 추출 중... 20%")
                    records = process_documents(inputs)
                    progress.progress(0.45, text="논문 간 의미 유사도 분석 중... 45%")
                    changed = asyncio.run(group_documents_with_agent(records, settings))
                    progress.progress(0.9, text="AI 그룹 결과 검증 중... 90%")
                st.session_state["document_records"] = records
                st.success(f"{changed}개 파일의 주제를 분석해 유사 그룹으로 묶었습니다.")
            except (IntegrationError, ValueError) as exc:
                st.session_state["document_records"] = process_documents(inputs)
                for record in st.session_state["document_records"]:
                    record.suggested_category = "분석 대기"
                    record.confidence = 0.0
                    record.reason = "AI 분석에 실패했습니다. AI 연결 상태를 확인한 뒤 다시 시도하세요."
                    record.matched_keywords = ()
                    record.classification_source = "ai-unavailable"
                st.error(f"AI 분석에 실패했습니다. 주제 그룹을 만들지 않았습니다: {exc}")
        else:
            st.session_state["document_records"] = process_documents(inputs)
            for record in st.session_state["document_records"]:
                record.suggested_category = "분석 대기"
                record.confidence = 0.0
                record.reason = "AI 연결이 준비되지 않아 주제 그룹을 만들지 않았습니다."
                record.matched_keywords = ()
                record.classification_source = "ai-unavailable"
            st.warning(
                "AI 설정이 준비되지 않았습니다. 서버 환경변수 GITHUB_TOKEN을 설정한 뒤 "
                "Streamlit을 재시작하세요."
            )
        progress.progress(1.0, text=f"분류 완료... 100% ({len(inputs)}/{len(inputs)})")
        st.session_state["analyzed_upload_signature"] = upload_signature
        st.session_state.pop("organized_zip", None)
        st.session_state.pop("organized_folder", None)

    records = st.session_state.get("document_records")
    if not records:
        st.caption("파일을 선택하면 AI 주제 분석이 자동으로 시작됩니다.")
        return

    _render_steps(3)
    st.subheader("분류안 검토")
    problem_count = sum(record.processing_status != "ready" for record in records)
    if problem_count:
        st.warning(
            f"{problem_count}개 파일에 빈 내용, 미지원 형식 또는 읽기 오류가 있습니다. "
            "오류 열을 확인하세요. 해당 파일도 원본 바이트 그대로 ZIP에 포함됩니다."
        )

    _classification_summary(records)
    editor = st.data_editor(
        _rows(records),
        hide_index=True,
        use_container_width=True,
        disabled=[
            "ID",
            "원본 경로",
            "파일명",
            "처리 상태",
            "추천 분류",
            "분류 방식",
            "신뢰도",
            "분류 근거",
            "오류",
            "참고",
        ],
        column_config={
            "ID": None,
            "최종 분류": st.column_config.SelectboxColumn(
                "최종 분류",
                options=sorted(set(CATEGORIES) | {record.suggested_category for record in records}),
                required=True,
            ),
            "신뢰도": st.column_config.NumberColumn(format="%.2f"),
        },
        key="classification_review",
    )

    _render_steps(4)
    st.subheader("결과 내보내기")
    confirmed = st.checkbox(
        "분류 결과를 확인했으며, 원본과 별개의 ZIP 파일을 생성합니다.",
        key="archive_confirmation",
    )
    overrides = {
        str(row["ID"]): str(row["최종 분류"]) for row in _edited_rows(editor)
    }
    zip_column, folder_column = st.columns(2)
    with zip_column:
        create_zip = st.button("정리 ZIP 생성", disabled=not confirmed)
    with folder_column:
        copy_folder = st.button("분류별 폴더로 복사", disabled=not confirmed)

    if create_zip:
        try:
            st.session_state["organized_zip"] = create_organized_zip(records, overrides)
        except ValueError as exc:
            st.error(f"ZIP을 만들 수 없습니다: {exc}")

    if copy_folder:
        output_dir = (
            Path.cwd()
            / "organized-output"
            / datetime.now().strftime("%Y%m%d-%H%M%S")
        )
        try:
            created_dir = create_organized_folder(records, output_dir, overrides)
            st.session_state["organized_folder"] = str(created_dir)
        except ValueError as exc:
            st.error(f"폴더를 만들 수 없습니다: {exc}")

    if organized_folder := st.session_state.get("organized_folder"):
        st.success(f"분류별 폴더를 만들었습니다: {organized_folder}")

    archive_data = st.session_state.get("organized_zip")
    if archive_data:
        st.success("정리 결과가 준비되었습니다. 원본 파일은 변경되지 않았습니다.")
        st.download_button(
            "organized_documents.zip 다운로드",
            data=archive_data,
            file_name="organized_documents.zip",
            mime="application/zip",
            type="primary",
        )


if __name__ == "__main__":
    main()
