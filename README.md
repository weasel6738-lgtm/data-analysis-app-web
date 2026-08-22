# AI 문서 주제 분류 웹 앱

논문과 문서를 업로드하면 본문 내용을 AI가 분석해 연구 주제를 파악하고,
주제가 유사한 문서끼리 자동으로 그룹화하는 Streamlit 웹 앱입니다.
문서 형식이나 파일명보다 본문의 의미와 연구 내용을 우선합니다.

## 제공 기능

- 논문·문서 여러 개 업로드
- 본문 내용 기반의 연구 주제 분석
- 의미가 유사한 문서끼리 자동 그룹화
- AI가 그룹명과 분류 근거 생성
- 파일별 신뢰도와 처리 상태 표시
- 분류 결과 검토 및 수정
- 분류별 폴더 복사 또는 ZIP 다운로드
- GitHub Copilot SDK 또는 Microsoft Agent Framework 연결

## 구조

```text
backend/app/
  document_ai.py    AI 주제 분석 및 유사 문서 그룹화
  document_organizer.py  문서 추출과 안전한 결과 생성
  integrations.py   Agent Framework / Copilot SDK 어댑터
  config.py         환경 변수 설정
  main.py           FastAPI 라우트와 정적 프론트엔드 제공
backend/streamlit_app.py  문서 업로드 및 주제 그룹화 화면
frontend/           React + TypeScript + Vite 운영 화면
infra/main.bicep    Azure Container Apps 인프라
sample-data/        SYNTHETIC_DEMO로 표시된 공개 합성 CSV
```

자세한 설계는 [docs/architecture.md](docs/architecture.md), 배포 절차는
[docs/deployment.md](docs/deployment.md)를 참고하세요.

## 로컬 실행

Python 3.12 환경에서 프로젝트 루트 기준으로 실행합니다.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements-documents.txt
streamlit run backend/streamlit_app.py --server.address 127.0.0.1 --server.port 8501
```

브라우저에서 <http://127.0.0.1:8501>을 열고 논문 또는 문서 폴더를
업로드합니다. 파일을 올리면 AI 주제 분석이 자동으로 시작됩니다.

1. 파일을 업로드합니다.
2. AI가 본문을 분석해 주제를 파악하고 유사한 문서끼리 그룹화합니다.
3. 표의 `최종 분류` 열에서 필요한 항목을 직접 수정합니다.
4. 확인 체크박스를 선택하고 `분류별 폴더로 복사` 또는 `정리 ZIP 생성`을 누릅니다.
5. 로컬 실행에서는 `organized-output` 폴더를 확인하거나 ZIP을 내려받아 결과와 `manifest.csv`를 확인합니다.

지원 형식은 TXT, MD, CSV, XLSX, DOCX, PDF 및 일반 이미지입니다. 문서의
본문을 AI로 분석하면 미리 정한 문서 유형이
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
계속됩니다. 외부 AI를 사용할 때는 조직의 보안·데이터 정책 승인 후
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
