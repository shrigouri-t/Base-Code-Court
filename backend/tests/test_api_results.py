"""Result endpoint contract tests."""

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import app
from app.api.routes_results import scores as scores_route


def test_unfinished_results_are_not_ready():
    with TestClient(app) as client:
        response = client.get("/scores/does-not-exist")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "analysis_not_found"


def test_pdf_endpoint_requires_completed_analysis():
    with TestClient(app) as client:
        response = client.get("/reports/does-not-exist/pdf")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "analysis_not_found"


def test_pdf_view_endpoint_requires_completed_analysis():
    with TestClient(app) as client:
        response = client.get("/reports/does-not-exist/pdf/view")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "analysis_not_found"


def test_scores_response_includes_persisted_feature_impacts():
    impacts = [
        {"feature": "work_score", "label": "Work Signal", "impact": 14.2}
    ]
    row = SimpleNamespace(
        author_key="alice",
        display_name="Alice",
        display_email="alice@example.com",
        rank=1,
        score=74.2,
        base_score=66.6,
        share_of_team=100.0,
        penalty_multiplier=1.0,
        commits=3,
        credited_lines=100,
        surviving_lines=80,
        signals={},
        notes=[],
        feature_impacts=impacts,
    )

    class Service:
        def get_scores(self, _analysis_id):
            return SimpleNamespace(report_json={}), [row]

    response = scores_route("analysis-id", Service())

    assert response["ranking"][0]["feature_impacts"] == impacts
