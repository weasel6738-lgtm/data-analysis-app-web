"""Korean Streamlit UI for the offline document organizer."""

from __future__ import annotations

from typing import Any

import streamlit as st
from streamlit.errors import StreamlitAPIException

try:
    from app.document_organizer import (
        CATEGORIES,
        CATEGORY_KEYWORDS,
        InputDocument,
        create_organized_zip,
        process_documents,
    )
except ModuleNotFoundError:
    from backend.app.document_organizer import (
        CATEGORIES,
        CATEGORY_KEYWORDS,
        InputDocument,
        create_organized_zip,
        process_documents,
    )


STATUS_LABELS = {
    "ready": "처리 가능",
    "empty": "빈 문서",
    "unsupported": "지원하지 않음",
    "error": "오류",
}


def _upload_widget() -> tuple[list[Any], bool]:
    try:
        files = st.file_uploader(
            "정리할 폴더를 선택하세요",
            accept_multiple_files="directory",
            key="directory_upload",
            help="폴더 안의 파일을 여러 개 불러옵니다. 브라우저에 따라 상대 경로가 보존됩니다.",
        )
        return list(files or []), True
    except (TypeError, StreamlitAPIException):
        files = st.file_uploader(
            "정리할 파일을 여러 개 선택하세요",
            accept_multiple_files=True,
            key="multiple_upload",
            help="현재 Streamlit 버전에서는 폴더 선택을 지원하지 않아 여러 파일 선택으로 동작합니다.",
        )
        return list(files or []), False


def _keyword_editor() -> dict[str, tuple[str, ...]]:
    configured: dict[str, tuple[str, ...]] = {}
    with st.expander("분류 키워드 설정", expanded=False):
        st.caption("쉼표로 구분해 수정할 수 있습니다. 파일명 일치는 내용 일치보다 높은 점수를 받습니다.")
        for category in CATEGORIES:
            if category in {"이미지", "기타/분류불가"}:
                configured[category] = ()
                continue
            value = st.text_input(
                category,
                value=", ".join(CATEGORY_KEYWORDS[category]),
                key=f"keywords_{category}",
            )
            configured[category] = tuple(
                keyword.strip() for keyword in value.split(",") if keyword.strip()
            )
    return configured


def _rows(records: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "ID": record.document_id,
            "원본 경로": record.original_path,
            "파일명": record.original_name,
            "처리 상태": STATUS_LABELS.get(record.processing_status, record.processing_status),
            "추천 분류": record.suggested_category,
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


def main() -> None:
    st.set_page_config(page_title="문서 자동 분류", page_icon="🗂️", layout="wide")
    st.title("🗂️ 문서 자동 분류 도우미")
    st.write("문서의 파일명과 내용을 로컬 규칙으로 분석해 주제별 정리안을 만듭니다.")
    st.info(
        "브라우저 업로드는 원본 폴더의 **복사본**만 읽습니다. "
        "원본 파일을 이동·수정·삭제하지 않으며, 확인 후 새 ZIP 파일만 생성합니다."
    )

    keywords = _keyword_editor()
    uploaded_files, folder_supported = _upload_widget()
    if not folder_supported:
        st.caption("폴더 경로 대신 파일명만 보존될 수 있습니다.")

    if st.button("1. 분류안 만들기", type="primary", disabled=not uploaded_files):
        inputs = [
            InputDocument(path=uploaded.name, content=uploaded.getvalue())
            for uploaded in uploaded_files
        ]
        st.session_state["document_records"] = process_documents(inputs, keywords)
        st.session_state.pop("organized_zip", None)

    records = st.session_state.get("document_records")
    if not records:
        st.caption("파일을 선택한 뒤 분류안 만들기를 누르세요.")
        return

    st.subheader("2. 분류안 검토")
    problem_count = sum(record.processing_status != "ready" for record in records)
    if problem_count:
        st.warning(
            f"{problem_count}개 파일에 빈 내용, 미지원 형식 또는 읽기 오류가 있습니다. "
            "오류 열을 확인하세요. 해당 파일도 원본 바이트 그대로 ZIP에 포함됩니다."
        )

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
            "신뢰도",
            "분류 근거",
            "오류",
            "참고",
        ],
        column_config={
            "ID": None,
            "최종 분류": st.column_config.SelectboxColumn(
                "최종 분류", options=list(CATEGORIES), required=True
            ),
            "신뢰도": st.column_config.NumberColumn(format="%.2f"),
        },
        key="classification_review",
    )

    st.subheader("3. 안전한 결과 만들기")
    confirmed = st.checkbox(
        "분류 결과를 확인했으며, 원본과 별개의 ZIP 파일을 생성합니다.",
        key="archive_confirmation",
    )
    if st.button("정리 ZIP 생성", disabled=not confirmed):
        overrides = {
            str(row["ID"]): str(row["최종 분류"]) for row in _edited_rows(editor)
        }
        try:
            st.session_state["organized_zip"] = create_organized_zip(records, overrides)
        except ValueError as exc:
            st.error(f"ZIP을 만들 수 없습니다: {exc}")

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
