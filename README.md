# FabriQ — 양산기술 AI 워크벤치

양산기술 엔지니어가 수율 변동을 읽고, 공정 이슈를 분류하고, 원인 후보와
검증 순서를 정리하는 웹 MVP입니다. **내장 데이터는 전부 제품 시연용 합성
데이터이며 SK hynix의 실제 또는 기밀 데이터를 포함하지 않습니다.**

## 제공 기능

- 수율/추세 분석과 3σ SPC 관리선, 이탈 및 연속 추세 탐지
- 공정 이슈 트리아지, SPC/FDC 스타일 신호 해석
- 수율과 공정 인자 간 상관 기반 원인 후보 순위(인과로 표현하지 않음)
- 관찰·가설·검증계획을 구분한 불량 원인 조사
- 대책 및 보고서 초안 워크플로
- Microsoft Agent Framework 오케스트레이션과 GitHub Copilot SDK 보고서 작성
- 외부 SDK/자격 증명이 없을 때 동작하는 결정론적 로컬 모드
- 파일 내용 기반의 오프라인 문서 자동 분류 및 안전한 ZIP 내보내기

## 구조

```text
backend/app/
  analysis.py       CSV, SPC, 상관 및 신호 분석
  document_organizer.py  문서 추출, 규칙 분류, 안전한 ZIP 생성
  orchestration.py  5개 양산기술 워크플로 서비스
  integrations.py   Agent Framework / Copilot SDK 지연 로딩 어댑터
  config.py         환경 변수 설정
  main.py           FastAPI 라우트와 정적 프론트엔드 제공
backend/streamlit_app.py  독립 실행형 문서 자동 분류 화면
frontend/           React + TypeScript + Vite 운영 화면
infra/main.bicep    Azure Container Apps 인프라
sample-data/        SYNTHETIC_DEMO로 표시된 공개 합성 CSV
```

자세한 설계는 [docs/architecture.md](docs/architecture.md), 배포 절차는
[docs/deployment.md](docs/deployment.md)를 참고하세요.

## 로컬 실행

Python 3.12 및 Node.js 20+가 필요합니다.

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

다른 터미널:

```powershell
cd frontend
npm install
npm run dev
```

<http://localhost:5173>을 엽니다. API 없이도 UI는 축약된 합성 데모로
전환됩니다. 또는 단일 컨테이너를 실행합니다.

```powershell
docker compose up --build
```

이 경우 <http://localhost:8000>에서 UI와 API를 함께 제공합니다.

## 문서 자동 분류 도우미 실행

문서 도우미는 기존 FastAPI/React 앱과 분리된 Streamlit 화면입니다. Python
3.12 환경에서 프로젝트 루트 기준으로 다음 명령을 실행합니다.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements-documents.txt
streamlit run backend\streamlit_app.py
```

브라우저에서 <http://localhost:8501>을 열고 폴더를 선택합니다. Streamlit
1.40 이상에서는 폴더 업로드를 사용하고, 지원하지 않는 환경에서는 여러 파일
선택으로 자동 전환됩니다. 브라우저가 전달한 상대 경로는 가능한 경우
보존됩니다.

1. `분류안 만들기`를 눌러 파일명과 문서 내용을 분석합니다.
2. 표의 `최종 분류` 열에서 필요한 항목을 직접 수정합니다.
3. 확인 체크박스를 선택하고 `분류별 폴더로 복사` 또는 `정리 ZIP 생성`을 누릅니다.
4. 로컬 실행에서는 `organized-output` 폴더를 확인하거나 ZIP을 내려받아 결과와 `manifest.csv`를 확인합니다.

지원 형식은 TXT, MD, CSV, XLSX, DOCX, PDF 및 일반 이미지입니다. 문서의
본문을 Microsoft Agent Framework를 통해 분석하면 미리 정한 문서 유형이
아니라 연구 주제·핵심 문제·방법론이 비슷한 파일끼리 AI가 새 그룹명을
만들어 묶습니다. 예를 들어 논문은 자연어 처리, 의료 영상 분석, 강화학습
등의 주제로 자동 그룹화할 수 있습니다. AI 설정이 없으면 주제 그룹을
생성하지 않고 설정 필요 상태로 표시합니다.

업로드된 데이터는 원본의 브라우저 복사본입니다. 앱은 원본을 이동하거나
삭제하지 않고 새 ZIP만 만듭니다. 빈 파일, 지원하지 않는 형식, 손상되거나
암호화된 파일은 개별 오류로 표시되며 나머지 파일 처리는 계속됩니다. ZIP
내부 경로는 별도로 검증하고 같은 파일명에는 `(2)`, `(3)`과 같은 번호를
붙입니다. `manifest.csv`에는 원본 경로, 추천/최종 분류, 신뢰도와 근거,
처리 상태 및 오류가 기록됩니다.

## 환경 설정

`.env.example`을 `.env`로 복사합니다. 기본값은 외부 전송이 없는 로컬 모드입니다.

| 변수 | 기본값 | 설명 |
|---|---|---|
| `ORCHESTRATOR_PROVIDER` | `local` | `local` 또는 `microsoft-agent` |
| `DRAFT_PROVIDER` | `local` | `local` 또는 `github-copilot` |
| `AZURE_OPENAI_ENDPOINT` | 빈 값 | Azure OpenAI 엔드포인트 |
| `AZURE_OPENAI_DEPLOYMENT` | 빈 값 | 채팅 모델 배포 이름 |
| `AZURE_OPENAI_API_KEY` | 빈 값 | 키 인증 시 사용. 배포 환경은 관리 ID 권장 |
| `GITHUB_TOKEN` | 빈 값 | Copilot SDK 인증 또는 Copilot CLI 인증 사용 |
| `COPILOT_MODEL` | `gpt-5` | Copilot SDK 세션 모델 |
| `CORS_ORIGINS` | localhost | 쉼표로 구분한 허용 origin |
| `MAX_UPLOAD_MB` | `10` | 1~100 MB |

AI 경로를 사용할 때만 공식 선택 패키지를 설치합니다.

```powershell
pip install -r backend/requirements.txt -r backend/requirements-ai.txt
```

`agent-framework`의 `AzureOpenAIChatClient`가 분석 단계를 오케스트레이션하고,
`github-copilot-sdk`의 `CopilotClient`가 보고서 워크플로 문안을 작성합니다.
패키지 또는 설정 오류는 명시적인 `fallback` 상태로 반환되며 기본 분석은
계속됩니다. 운영 데이터 외부 전송은 조직의 보안·데이터 정책 승인 후
명시적으로 provider를 바꾼 경우에만 허용해야 합니다.

## API

- `GET /api/health` — 상태 확인
- `GET /api/config` — 비밀값을 제외한 integration 상태
- `GET /api/dashboard` — 합성 데모 분석
- `POST /api/analyze` — UTF-8 CSV 업로드
- `POST /api/workflows` — `yield-trend`, `issue-triage`, `spc-fdc`,
  `root-cause`, `report`
- `/docs` — OpenAPI UI

## 검증

```powershell
python -m pytest backend/tests -q
python -m pytest backend/tests/test_document_organizer.py -q
python -m streamlit run backend/streamlit_app.py --server.headless true
cd frontend
npm run build
```

어떤 분석 결과도 공정 승인이나 자동 제어 명령으로 사용하지 마세요. 현장
원데이터, 계측 건전성, 제품/설비별 층별화를 엔지니어가 확인해야 합니다.
