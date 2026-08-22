import { ChangeEvent, DragEvent, useEffect, useMemo, useRef, useState } from "react";

type Severity = "critical" | "warning" | "normal";
type WorkflowKind = "yield-trend" | "issue-triage" | "spc-fdc" | "root-cause" | "report";
type Signal = { severity: Severity; title: string; detail: string };
type Correlation = { factor: string; correlation: number; direction: string };
type Spc = {
  column: string; center: number; ucl: number; lcl: number; sigma: number;
  violations: number[]; trend: string; delta: number;
};
type Analysis = {
  filename: string; rowCount: number; columnCount: number; columns: string[];
  numericStats: { column: string; count: number; mean: number; min: number; max: number; stdDev: number }[];
  chartData: { label: string; value: number }[];
  preview: Record<string, string>[];
  manufacturing: {
    yieldColumn: string | null; defectColumn: string | null; spc: Spc | null;
    signals: Signal[]; correlations: Correlation[];
  };
  isSynthetic: boolean; dataNotice?: string;
};
type WorkflowResult = {
  title: string; summary: string; observations: string[]; hypotheses: string[];
  nextSteps: string[]; notice: string; provider: string; status: string;
  providerNotice: string; generatedNarrative?: string;
};

const API_URL = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");
const workflows: { kind: WorkflowKind; label: string; short: string }[] = [
  { kind: "yield-trend", label: "수율·추세 분석", short: "수율" },
  { kind: "issue-triage", label: "공정 이슈 트리아지", short: "트리아지" },
  { kind: "spc-fdc", label: "SPC/FDC 신호 해석", short: "SPC/FDC" },
  { kind: "root-cause", label: "불량 원인 조사", short: "원인 조사" },
  { kind: "report", label: "대책·보고서 초안", short: "보고서" },
];

const fallback: Analysis = {
  filename: "synthetic-fab-yield-demo.csv", rowCount: 12, columnCount: 8,
  columns: ["date", "lot_id", "equipment", "yield_pct", "defect_ppm"],
  numericStats: [],
  chartData: [96.8, 96.5, 96.7, 96.2, 96.4, 95.9, 95.6, 95.2, 94.9, 93.8, 93.4, 92.8]
    .map((value, index) => ({ label: `07-${String(index + 1).padStart(2, "0")}`, value })),
  preview: [],
  manufacturing: {
    yieldColumn: "yield_pct", defectColumn: "defect_ppm",
    spc: { column: "yield_pct", center: 95.35, ucl: 98.66, lcl: 92.04, sigma: 1.1, violations: [], trend: "하락", delta: -3.2 },
    signals: [{ severity: "warning", title: "수율 하락 추세", detail: "최근 구간에서 수율 저하가 이어집니다. 설비·레시피별 층별화가 필요합니다." }],
    correlations: [
      { factor: "chamber_pressure_mtorr", correlation: -0.94, direction: "반대로 이동" },
      { factor: "temperature_c", correlation: -0.91, direction: "반대로 이동" },
      { factor: "etch_rate_nm_min", correlation: -0.89, direction: "반대로 이동" },
    ],
  },
  isSynthetic: true,
  dataNotice: "이 화면의 모든 값과 식별자는 제품 시연용 합성 데이터입니다.",
};

const format = (value: number, digits = 1) =>
  new Intl.NumberFormat("ko-KR", { maximumFractionDigits: digits }).format(value);

export default function App() {
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [selected, setSelected] = useState<WorkflowKind>("issue-triage");
  const [result, setResult] = useState<WorkflowResult | null>(null);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [workflowBusy, setWorkflowBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const autoRunSource = useRef<Analysis | null>(null);

  useEffect(() => {
    fetch(`${API_URL}/api/dashboard`)
      .then((response) => response.ok ? response.json() : Promise.reject())
      .then(setAnalysis)
      .catch(() => setAnalysis(fallback));
  }, []);

  useEffect(() => {
    if (analysis && autoRunSource.current !== analysis) {
      autoRunSource.current = analysis;
      void runWorkflow("issue-triage", analysis);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [analysis]);

  async function analyzeFile(file: File) {
    setError("");
    if (!file.name.toLowerCase().endsWith(".csv")) {
      setError("CSV 형식의 파일을 선택해 주세요.");
      return;
    }
    setBusy(true);
    const body = new FormData();
    body.append("file", file);
    try {
      const response = await fetch(`${API_URL}/api/analyze`, { method: "POST", body });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "데이터를 분석하지 못했습니다.");
      setAnalysis(payload);
      setResult(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "API 연결을 확인해 주세요.");
    } finally {
      setBusy(false);
    }
  }

  async function runWorkflow(kind: WorkflowKind, source = analysis) {
    if (!source) return;
    setSelected(kind);
    setWorkflowBusy(true);
    setError("");
    try {
      const response = await fetch(`${API_URL}/api/workflows`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ kind, context: source, question }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "워크플로를 실행하지 못했습니다.");
      setResult(payload);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "워크플로 실행에 실패했습니다.");
      setResult(localWorkflow(kind, source));
    } finally {
      setWorkflowBusy(false);
    }
  }

  function onInput(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (file) void analyzeFile(file);
    event.target.value = "";
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    const file = event.dataTransfer.files[0];
    if (file) void analyzeFile(file);
  }

  const spc = analysis?.manufacturing.spc;
  const chartData = analysis?.chartData || [];
  const latest = chartData[chartData.length - 1]?.value;
  const first = chartData[0]?.value;
  const delta = latest != null && first != null ? latest - first : null;

  return (
    <div className="app-frame">
      <aside className="rail">
        <div className="logo" aria-label="FabriQ">
          <span className="logo-glyph">FQ</span>
          <span><strong>FabriQ</strong><small>양산기술 AI 워크벤치</small></span>
        </div>
        <nav aria-label="워크플로">
          <span className="nav-label">분석 워크플로</span>
          {workflows.map((workflow) => (
            <button
              className={selected === workflow.kind ? "nav-item active" : "nav-item"}
              key={workflow.kind}
              onClick={() => void runWorkflow(workflow.kind)}
            >
              <i aria-hidden="true" /> {workflow.label}
            </button>
          ))}
        </nav>
        <div className="rail-foot">
          <span className="connection"><i /> DEMO READY</span>
          <p>외부 AI는 명시적으로 설정한 경우에만 호출됩니다.</p>
        </div>
      </aside>

      <main className="workspace">
        <header className="toolbar">
          <div>
            <h1>양산 현황 브리핑</h1>
            <p>{analysis?.filename || "데이터를 불러오는 중입니다"}</p>
          </div>
          <div className="toolbar-actions">
            <span className="updated">
              {analysis?.isSynthetic ? "합성 데모 · 2026.07.24 기준" : analysis ? `${analysis.rowCount}행 · 업로드 데이터` : "준비 중"}
            </span>
            <button className="upload-button" onClick={() => inputRef.current?.click()} disabled={busy}>
              <UploadIcon /> {busy ? "분석 중…" : "CSV 가져오기"}
            </button>
            <input ref={inputRef} type="file" accept=".csv,text/csv" onChange={onInput} hidden />
          </div>
        </header>

        {analysis?.isSynthetic && (
          <div className="synthetic-notice" role="note">
            <span>DEMO DATA</span>
            <p>{analysis.dataNotice}</p>
          </div>
        )}
        {error && <div className="error-line" role="alert">{error}</div>}

        {!analysis ? <LoadingState /> : (
          <>
            <section
              className={dragging ? "briefing dragging" : "briefing"}
              onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onDrop={onDrop}
            >
              <div className="brief-head">
                <div>
                  <h2>수율 추이와 관리선</h2>
                  <p>일별 Lot 평균 · {spc?.column || "측정값"} · 3σ 기준</p>
                </div>
                <div className="metric-row">
                  <Metric label="최근 수율" value={latest == null ? "—" : `${format(latest)}%`} />
                  <Metric label="기간 변화" value={delta == null ? "—" : `${delta > 0 ? "+" : ""}${format(delta)}%p`} tone={delta != null && delta < 0 ? "bad" : "good"} />
                  <Metric label="관리선 이탈" value={`${spc?.violations.length || 0} Lot`} tone={(spc?.violations.length || 0) > 0 ? "bad" : "good"} />
                </div>
              </div>
              <TrendChart points={analysis.chartData} spc={spc} />
              {dragging && <div className="drop-overlay">CSV를 놓아 새 분석 시작</div>}
            </section>

            <section className="decision-grid">
              <div className="signal-column">
                <div className="section-title">
                  <h2>오늘 확인할 신호</h2>
                  <span>{analysis.manufacturing.signals.length}건 감지</span>
                </div>
                <div className="signal-list">
                  {analysis.manufacturing.signals.map((signal, index) => (
                    <article className={`signal ${signal.severity}`} key={`${signal.title}-${index}`}>
                      <span className="signal-status">{severityLabel(signal.severity)}</span>
                      <div><h3>{signal.title}</h3><p>{signal.detail}</p></div>
                      <span className="arrow" aria-hidden="true">↗</span>
                    </article>
                  ))}
                </div>
                <div className="section-title factor-title">
                  <h2>원인 후보 우선순위</h2><span>상관 기반 · 인과 아님</span>
                </div>
                <div className="factor-table" role="table" aria-label="원인 후보 상관 순위">
                  {analysis.manufacturing.correlations.map((item, index) => (
                    <div className="factor-row" role="row" key={item.factor}>
                      <span className="rank">{String(index + 1).padStart(2, "0")}</span>
                      <strong>{humanize(item.factor)}</strong>
                      <div className="correlation-track"><i style={{ width: `${Math.abs(item.correlation) * 100}%` }} /></div>
                      <span className={item.correlation < 0 ? "negative" : "positive"}>{item.correlation > 0 ? "+" : ""}{item.correlation.toFixed(2)}</span>
                    </div>
                  ))}
                </div>
              </div>

              <WorkflowPanel
                selected={selected}
                result={result}
                busy={workflowBusy}
                question={question}
                setQuestion={setQuestion}
                run={() => void runWorkflow(selected)}
              />
            </section>
          </>
        )}
        <footer>
          <span>FabriQ MVP · 제조 의사결정 보조</span>
          <span>{analysis?.isSynthetic ? "합성 데이터 · 실제 현장 검증 필수" : "사용자 업로드 · 외부 전송 설정 확인"}</span>
        </footer>
      </main>
    </div>
  );
}

function TrendChart({ points, spc }: { points: Analysis["chartData"]; spc: Spc | null | undefined }) {
  const geometry = useMemo(() => {
    if (!points.length) return null;
    const all = [...points.map((point) => point.value), spc?.ucl || 0, spc?.lcl || Infinity].filter(Number.isFinite);
    const min = Math.min(...all) - 0.4;
    const max = Math.max(...all) + 0.4;
    const x = (index: number) => 52 + (index / Math.max(points.length - 1, 1)) * 674;
    const y = (value: number) => 18 + ((max - value) / Math.max(max - min, 0.1)) * 176;
    return { min, max, x, y, path: points.map((point, index) => `${x(index)},${y(point.value)}`).join(" ") };
  }, [points, spc]);
  if (!geometry) return <div className="chart-empty">수치 열이 있는 CSV를 가져오면 추세를 표시합니다.</div>;
  return (
    <div className="chart-wrap">
      <svg viewBox="0 0 760 230" role="img" aria-label="수율 추세와 SPC 관리한계">
        {[0, 1, 2, 3].map((line) => <line className="grid-line" key={line} x1="52" x2="726" y1={18 + line * 58.6} y2={18 + line * 58.6} />)}
        {spc && <>
          <line className="limit-line" x1="52" x2="726" y1={geometry.y(spc.ucl)} y2={geometry.y(spc.ucl)} />
          <text className="limit-label" x="54" y={geometry.y(spc.ucl) - 5}>UCL {format(spc.ucl, 2)}</text>
          <line className="center-line" x1="52" x2="726" y1={geometry.y(spc.center)} y2={geometry.y(spc.center)} />
          <text className="center-label" x="724" textAnchor="end" y={geometry.y(spc.center) - 5}>CL {format(spc.center, 2)}</text>
          <line className="limit-line" x1="52" x2="726" y1={geometry.y(spc.lcl)} y2={geometry.y(spc.lcl)} />
        </>}
        <polyline className="trend-area" points={`52,194 ${geometry.path} 726,194`} />
        <polyline className="trend-line" points={geometry.path} />
        {points.map((point, index) => (
          <circle className={spc?.violations.includes(index) ? "chart-dot violation" : "chart-dot"} key={`${point.label}-${index}`} cx={geometry.x(index)} cy={geometry.y(point.value)} r="3.5">
            <title>{point.label}: {point.value}%</title>
          </circle>
        ))}
        <text className="axis-label" x="8" y="24">{format(geometry.max)}</text>
        <text className="axis-label" x="8" y="197">{format(geometry.min)}</text>
        {points.filter((_, index) => index % Math.max(Math.floor(points.length / 6), 1) === 0).map((point, index) => (
          <text className="axis-label" key={point.label} x={geometry.x(index * Math.max(Math.floor(points.length / 6), 1))} y="220" textAnchor="middle">{point.label.slice(5)}</text>
        ))}
      </svg>
      <div className="chart-legend"><span><i className="legend-yield" />수율</span><span><i className="legend-limit" />관리한계</span><span><i className="legend-center" />중심선</span></div>
    </div>
  );
}

function WorkflowPanel({ selected, result, busy, question, setQuestion, run }: {
  selected: WorkflowKind; result: WorkflowResult | null; busy: boolean; question: string;
  setQuestion: (value: string) => void; run: () => void;
}) {
  const title = workflows.find((item) => item.kind === selected)?.label;
  return (
    <aside className="workflow-panel">
      <div className="workflow-head">
        <div><span className="agent-mark">AI</span><h2>{title}</h2></div>
        <span className="provider">{result?.provider || "local"}</span>
      </div>
      {busy ? <div className="workflow-loading"><i /><p>관찰과 가설을 분리하고 있습니다…</p></div> : result ? (
        <div className="workflow-body">
          <p className="workflow-summary">{result.summary}</p>
          <h3>확인된 관찰</h3>
          <ul>{result.observations.map((item, index) => <li key={index}>{item}</li>)}</ul>
          <h3>우선 검증 가설</h3>
          <ol>{result.hypotheses.slice(0, 3).map((item, index) => <li key={index}><span>{index + 1}</span>{item}</li>)}</ol>
          <h3>다음 조치</h3>
          <div className="steps">{result.nextSteps.map((item, index) => <label key={index}><input type="checkbox" />{item}</label>)}</div>
          {result.generatedNarrative && <pre className="generated">{result.generatedNarrative}</pre>}
          <p className="provider-notice">{result.providerNotice}</p>
        </div>
      ) : null}
      <div className="ask-row">
        <input value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="추가 조건 또는 확인할 질문" onKeyDown={(event) => { if (event.key === "Enter") run(); }} />
        <button onClick={run} disabled={busy} aria-label="질문 실행">→</button>
      </div>
      <p className="verification">AI 제안은 현장 원데이터와 엔지니어 검증 후 적용하세요.</p>
    </aside>
  );
}

function Metric({ label, value, tone = "" }: { label: string; value: string; tone?: string }) {
  return <div className="metric"><span>{label}</span><strong className={tone}>{value}</strong></div>;
}
function LoadingState() {
  return <div className="loading-state"><i /><strong>합성 데모 데이터를 준비하고 있습니다</strong><p>API가 없으면 브라우저 내 데모로 전환합니다.</p></div>;
}
function UploadIcon() {
  return <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M10 13V3m0 0L6.5 6.5M10 3l3.5 3.5M3 12.5V17h14v-4.5" /></svg>;
}
function severityLabel(severity: Severity) {
  return severity === "critical" ? "긴급" : severity === "warning" ? "주의" : "정상";
}
function humanize(value: string) {
  const labels: Record<string, string> = {
    defect_ppm: "Defect PPM", etch_rate_nm_min: "Etch rate",
    chamber_pressure_mtorr: "Chamber pressure", temperature_c: "Temperature",
    cd_nm: "CD", overlay_nm: "Overlay",
  };
  return labels[value] || value.replace(/_/g, " ");
}
function localWorkflow(kind: WorkflowKind, source: Analysis): WorkflowResult {
  const signal = source.manufacturing.signals[0];
  return {
    title: workflows.find((item) => item.kind === kind)?.label || "분석",
    summary: signal?.detail || "로컬 데이터에서 명확한 이상 신호를 찾지 못했습니다.",
    observations: [signal?.detail || "추가 데이터가 필요합니다."],
    hypotheses: source.manufacturing.correlations.slice(0, 3).map((item) => `${humanize(item.factor)} 조건 영향`),
    nextSteps: ["영향 Lot 범위 확인", "설비·레시피별 층별화", "정상 Lot과 비교 검증"],
    notice: "현장 검증 필요", provider: "browser-local", status: "fallback",
    providerNotice: "API에 연결할 수 없어 브라우저 로컬 결과를 표시합니다.",
  };
}
