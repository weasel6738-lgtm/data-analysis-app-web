"""Deterministic manufacturing analysis used by API and offline demo mode."""

from __future__ import annotations

import csv
import io
import math
import statistics
from dataclasses import dataclass
from typing import Any

MAX_CHART_POINTS = 120
YIELD_ALIASES = ("yield_pct", "yield", "수율")
DEFECT_ALIASES = ("defect_ppm", "defect", "불량")


@dataclass
class DatasetAnalysis:
    filename: str
    row_count: int
    column_count: int
    columns: list[str]
    numeric_stats: list[dict[str, Any]]
    chart_data: list[dict[str, Any]]
    preview: list[dict[str, Any]]
    manufacturing: dict[str, Any]
    is_synthetic: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "filename": self.filename,
            "rowCount": self.row_count,
            "columnCount": self.column_count,
            "columns": self.columns,
            "numericStats": self.numeric_stats,
            "chartData": self.chart_data,
            "preview": self.preview,
            "manufacturing": self.manufacturing,
            "isSynthetic": self.is_synthetic,
        }


def _number(value: str) -> float | None:
    cleaned = value.strip().replace(",", "").replace("%", "")
    if not cleaned:
        return None
    try:
        parsed = float(cleaned)
    except ValueError:
        return None
    return parsed if math.isfinite(parsed) else None


def _find_column(columns: list[str], aliases: tuple[str, ...]) -> str | None:
    normalized = {column.lower().strip(): column for column in columns}
    for alias in aliases:
        if alias in normalized:
            return normalized[alias]
    return None


def _pearson(left: list[float], right: list[float]) -> float | None:
    if len(left) < 3 or len(left) != len(right):
        return None
    left_mean, right_mean = statistics.mean(left), statistics.mean(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right))
    denominator = math.sqrt(
        sum((x - left_mean) ** 2 for x in left) * sum((y - right_mean) ** 2 for y in right)
    )
    return numerator / denominator if denominator else None


def _manufacturing_analysis(
    rows: list[dict[str, str]], columns: list[str], numeric_columns: list[str]
) -> dict[str, Any]:
    yield_column = _find_column(columns, YIELD_ALIASES)
    defect_column = _find_column(columns, DEFECT_ALIASES)
    measure_column = yield_column or defect_column or (numeric_columns[0] if numeric_columns else None)
    values = [
        value
        for row in rows
        if measure_column and (value := _number(row[measure_column])) is not None
    ]
    spc: dict[str, Any] | None = None
    signals: list[dict[str, str]] = []

    if values:
        center = statistics.mean(values)
        sigma = statistics.stdev(values) if len(values) > 1 else 0.0
        ucl = center + 3 * sigma
        lcl = max(0.0, center - 3 * sigma)
        violations = [index for index, value in enumerate(values) if value > ucl or value < lcl]
        recent = statistics.mean(values[-3:])
        earlier = statistics.mean(values[:3])
        direction = "상승" if recent > earlier else "하락" if recent < earlier else "보합"
        spc = {
            "column": measure_column,
            "center": round(center, 4),
            "ucl": round(ucl, 4),
            "lcl": round(lcl, 4),
            "sigma": round(sigma, 4),
            "violations": violations,
            "trend": direction,
            "delta": round(recent - earlier, 4),
        }
        if violations:
            signals.append(
                {
                    "severity": "critical",
                    "title": "관리한계 이탈 감지",
                    "detail": f"{measure_column}에서 {len(violations)}개 포인트가 3σ 관리한계를 벗어났습니다.",
                }
            )
        elif len(values) >= 6 and all(
            values[index] <= values[index - 1] for index in range(len(values) - 5, len(values))
        ):
            signals.append(
                {
                    "severity": "warning",
                    "title": "연속 하락 패턴",
                    "detail": f"{measure_column}이 최근 6개 구간에서 연속 하락했습니다.",
                }
            )
        elif recent < earlier - sigma:
            signals.append(
                {
                    "severity": "warning",
                    "title": "기준 대비 하락 추세",
                    "detail": (
                        f"{measure_column}의 최근 평균이 초기 평균보다 "
                        f"{abs(recent - earlier):.2f} 낮습니다."
                    ),
                }
            )
        else:
            signals.append(
                {
                    "severity": "normal",
                    "title": "공정 변동 안정",
                    "detail": f"{measure_column}에 명확한 3σ 이탈은 없습니다. 추세는 {direction}입니다.",
                }
            )

    target = yield_column or defect_column
    correlations: list[dict[str, Any]] = []
    if target:
        for column in numeric_columns:
            if column in {target, yield_column, defect_column}:
                continue
            pairs = [
                (target_value, factor_value)
                for row in rows
                if (target_value := _number(row[target])) is not None
                and (factor_value := _number(row[column])) is not None
            ]
            correlation = _pearson([pair[0] for pair in pairs], [pair[1] for pair in pairs])
            if correlation is not None:
                correlations.append(
                    {
                        "factor": column,
                        "correlation": round(correlation, 3),
                        "direction": "같이 증가" if correlation > 0 else "반대로 이동",
                    }
                )
        correlations.sort(key=lambda item: abs(item["correlation"]), reverse=True)

    return {
        "yieldColumn": yield_column,
        "defectColumn": defect_column,
        "spc": spc,
        "signals": signals,
        "correlations": correlations[:5],
    }


def analyze_csv(
    content: bytes | str, filename: str = "dataset.csv", *, is_synthetic: bool = False
) -> DatasetAnalysis:
    """Parse CSV content and return bounded statistics and manufacturing signals."""

    text = content.decode("utf-8-sig") if isinstance(content, bytes) else content
    if not text.strip():
        raise ValueError("CSV 파일이 비어 있습니다.")
    try:
        dialect = csv.Sniffer().sniff(text[:4096])
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames:
        raise ValueError("CSV에는 하나 이상의 열 이름이 필요합니다.")
    source_columns = [str(column) for column in reader.fieldnames]
    columns = [column.strip() for column in source_columns]
    if len(set(columns)) != len(columns):
        raise ValueError("CSV 열 이름은 중복될 수 없습니다.")
    if any(not column for column in columns):
        raise ValueError("모든 CSV 열에 이름이 필요합니다.")

    rows: list[dict[str, str]] = []
    for raw_row in reader:
        row = {
            column: (raw_row.get(source_column) or "").strip()
            for source_column, column in zip(source_columns, columns)
        }
        if any(row.values()):
            rows.append(row)
    if not rows:
        raise ValueError("CSV에 분석할 데이터 행이 없습니다.")

    numeric_stats: list[dict[str, Any]] = []
    numeric_columns: list[str] = []
    for column in columns:
        populated = [row[column] for row in rows if row[column]]
        values = [value for value in (_number(item) for item in populated) if value is not None]
        if values and len(values) == len(populated):
            numeric_columns.append(column)
            mean = statistics.mean(values)
            numeric_stats.append(
                {
                    "column": column,
                    "count": len(values),
                    "mean": round(mean, 4),
                    "min": min(values),
                    "max": max(values),
                    "stdDev": round(statistics.stdev(values), 4) if len(values) > 1 else 0,
                }
            )

    manufacturing = _manufacturing_analysis(rows, columns, numeric_columns)
    chart_column = manufacturing["yieldColumn"] or (
        numeric_columns[0] if numeric_columns else None
    )
    chart_data = []
    if chart_column:
        for index, row in enumerate(rows[:MAX_CHART_POINTS], start=1):
            value = _number(row[chart_column])
            if value is not None:
                chart_data.append(
                    {
                        "label": row[columns[0]] or f"Row {index}",
                        "value": value,
                    }
                )

    return DatasetAnalysis(
        filename=filename,
        row_count=len(rows),
        column_count=len(columns),
        columns=columns,
        numeric_stats=numeric_stats,
        chart_data=chart_data,
        preview=rows[:10],
        manufacturing=manufacturing,
        is_synthetic=is_synthetic,
    )
