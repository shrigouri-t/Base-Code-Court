from app.core.pdf_export import available_signal_names, report_to_pdf


def test_report_to_pdf_returns_valid_document():
    pdf = report_to_pdf(
        {
            "meta": {
                "repo": "owner/repository",
                "head_sha": "abc123",
                "generated_at": "2026-11-21T00:00:00+00:00",
            },
            "effective_weights": {"work": 0.45, "survival": 0.25},
            "available_signals": ["work", "survival"],
            "dropped_signals": {"review": "not collected"},
            "anomalies": [],
            "authors": [
                {
                    "author_key": "contributor@example.com",
                    "signals": {
                        "work": {"available": True, "score": 0.8, "points": 44.0},
                        "survival": {"available": True, "score": 0.7, "points": 34.0},
                    },
                }
            ],
        },
        [
            {
                "rank": 1,
                "display_name": "Contributor",
                "author_key": "contributor@example.com",
                "score": 95.5,
                "share_of_team": 100.0,
                "commits": 10,
                "surviving_lines": 300,
                "base_score": 95.5,
            }
        ],
    )
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 1000
    assert available_signal_names({
        "available_signals": ["work", "survival"],
        "dropped_signals": {"review": "not collected"},
    }) == ["work", "survival"]
