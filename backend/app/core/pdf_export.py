"""PDF export for completed contribution reports."""

from io import BytesIO
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from reportlab.graphics.charts.barcharts import HorizontalBarChart
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

_SIGNAL_LABELS = {
    "work": "Work",
    "survival": "Survival",
    "ownership": "Ownership",
    "review": "Review",
    "issues": "Issues",
    "consistency": "Consistency",
}
_NAVY = colors.HexColor("#172b4d")
_TEAL = colors.HexColor("#168c85")
_MUTED = colors.HexColor("#64748b")


def available_signal_names(
    report: dict[str, Any],
    ranking: list[dict[str, Any]] | None = None,
) -> list[str]:
    """Return only signals included in the repository's final score."""
    declared = report.get("available_signals")
    if declared is not None:
        return [name for name in _SIGNAL_LABELS if name in declared]

    effective_weights = report.get("effective_weights", {})
    if effective_weights:
        return [
            name for name in _SIGNAL_LABELS
            if effective_weights.get(name, 0) > 0
        ]

    authors = ranking or report.get("ranking") or report.get("authors", [])
    for author in authors:
        signals = author.get("signals", {})
        available = [
            name for name in _SIGNAL_LABELS
            if signals.get(name, {}).get("available", False)
        ]
        if available:
            return available
    return []


def _contributors(
    report: dict[str, Any],
    ranking: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    report_authors = report.get("authors", [])
    author_details = {
        author.get("author_key"): author
        for author in report_authors
        if author.get("author_key")
    }
    source = ranking or report.get("ranking") or report_authors
    contributors = []
    for row in source:
        details = author_details.get(row.get("author_key"), {})
        contributors.append({**details, **row})
    return sorted(
        contributors,
        key=lambda author: (
            author.get("rank", 10**9),
            author.get("display_name") or author.get("author_key") or "",
        ),
    )


def _signal_cell(author: dict[str, Any], name: str) -> str:
    signal = author.get("signals", {}).get(name)
    if not signal or not signal.get("available", True):
        return "—"
    score = float(signal.get("score", 0)) * 100
    points = signal.get("points")
    if points is None:
        return f"{score:.1f}%"
    return f"{score:.1f}%<br/><font color='#64748b' size='7'>{float(points):.2f} pts</font>"


def _score_chart(contributors: list[dict[str, Any]]) -> Drawing | None:
    chart_authors = contributors[:12]
    if not chart_authors:
        return None

    chart_height = max(115, 18 * len(chart_authors))
    drawing = Drawing(730, chart_height + 52)
    chart = HorizontalBarChart()
    chart.x = 145
    chart.y = 25
    chart.width = 535
    chart.height = chart_height
    chart.data = [[float(author.get("score", 0)) for author in chart_authors]]
    chart.categoryAxis.categoryNames = [
        str(author.get("display_name") or author.get("author_key") or "Contributor")
        for author in chart_authors
    ]
    chart.categoryAxis.labels.fontName = "Helvetica"
    chart.categoryAxis.labels.fontSize = 8
    chart.categoryAxis.labels.fillColor = _NAVY
    chart.categoryAxis.labels.dx = -5
    chart.valueAxis.valueMin = 0
    chart.valueAxis.valueMax = 100
    chart.valueAxis.valueStep = 20
    chart.valueAxis.labels.fontName = "Helvetica"
    chart.valueAxis.labels.fontSize = 8
    chart.valueAxis.labels.fillColor = _MUTED
    chart.valueAxis.strokeColor = colors.HexColor("#cbd5e1")
    chart.valueAxis.gridStrokeColor = colors.HexColor("#e2e8f0")
    chart.bars[0].fillColor = _TEAL
    chart.bars[0].strokeColor = _TEAL
    chart.barWidth = 9
    chart.barSpacing = 3
    drawing.add(chart)
    return drawing


def report_to_pdf(
    report: dict[str, Any],
    ranking: list[dict[str, Any]] | None = None,
) -> bytes:
    """Render a signal comparison table and score chart as a PDF."""
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=34,
        leftMargin=34,
        topMargin=30,
        bottomMargin=30,
        title="CodeCourt Contribution Report",
        author="CodeCourt",
    )
    styles = getSampleStyleSheet()
    title_style = styles["Title"]
    title_style.alignment = TA_CENTER
    title_style.textColor = _NAVY
    body_style = styles["Normal"]
    elements = [
        Paragraph("CodeCourt Contribution Report", title_style),
        Spacer(1, 8),
    ]

    meta = report.get("meta", {})
    if meta:
        elements.append(Paragraph(
            f"<b>Repository:</b> {escape(str(meta.get('repo', 'N/A')))}"
            f"&nbsp;&nbsp;&nbsp; <b>HEAD:</b> {escape(str(meta.get('head_sha', 'N/A')))}"
            f"&nbsp;&nbsp;&nbsp; <b>Generated:</b> {escape(str(meta.get('generated_at', 'N/A')))}",
            body_style,
        ))
        elements.append(Spacer(1, 12))

    contributors = _contributors(report, ranking)
    signals = available_signal_names(report, contributors)
    elements.append(Paragraph("Contributor Signal Breakdown", styles["Heading2"]))
    if contributors:
        effective = report.get("effective_weights", {})
        headers = ["Rank", "Contributor"]
        headers.extend(
            f"{_SIGNAL_LABELS[name]} ({effective[name] * 100:.0f}%)"
            if name in effective else _SIGNAL_LABELS[name]
            for name in signals
        )
        headers.extend(["Base", "Final", "Team Share"])
        table_data = [headers]
        for author in contributors:
            row = [
                str(author.get("rank", "")),
                Paragraph(
                    escape(str(author.get("display_name") or author.get("author_key") or "")),
                    styles["BodyText"],
                ),
            ]
            row.extend(
                Paragraph(_signal_cell(author, name), styles["BodyText"])
                for name in signals
            )
            row.extend([
                f"{float(author.get('base_score', author.get('score', 0))):.2f}",
                f"{float(author.get('score', 0)):.2f}",
                f"{float(author.get('share_of_team', 0)):.1f}%",
            ])
            table_data.append(row)

        usable_width = landscape(A4)[0] - document.leftMargin - document.rightMargin
        fixed_width = 35 + 125 + 55 + 55 + 68
        signal_width = (usable_width - fixed_width) / max(1, len(signals))
        widths = [35, 125] + [signal_width] * len(signals) + [55, 55, 68]
        table = Table(table_data, colWidths=widths, repeatRows=1, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), _NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 8),
            ("ALIGN", (0, 0), (0, -1), "CENTER"),
            ("ALIGN", (2, 1), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#d5dee9")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [
                colors.white,
                colors.HexColor("#f4f7fb"),
            ]),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ]))
        elements.extend([table, Spacer(1, 18)])
    else:
        elements.append(Paragraph("No contributor rankings available.", body_style))

    elements.append(Paragraph("Final Score Comparison", styles["Heading2"]))
    chart = _score_chart(contributors)
    if chart is not None:
        elements.append(chart)
    else:
        elements.append(Paragraph("No scores available to chart.", body_style))

    document.build(elements)
    return buffer.getvalue()


def write_report_pdf(
    report: dict[str, Any],
    path: Path,
    ranking: list[dict[str, Any]] | None = None,
) -> None:
    """Write a PDF report to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(report_to_pdf(report, ranking))
