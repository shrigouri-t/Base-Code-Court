"""Persistence model tests."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError

from app.db.base import UTCDateTime, create_engine_from_url, init_db, make_session_factory
from app.db.models import Analysis, AnomalyRow, CommitRow, ContributorScore, Repository
from app.db import crud


def _session(tmp_path):
    engine = create_engine_from_url(f"sqlite:///{tmp_path / 'test.db'}")
    init_db(engine)
    return make_session_factory(engine), engine


def test_init_db_migrates_legacy_repository_columns(tmp_path):
    engine = create_engine_from_url(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE repositories ("
            "id INTEGER PRIMARY KEY, owner VARCHAR(100) NOT NULL, "
            "name VARCHAR(100) NOT NULL, created_at DATETIME NOT NULL)"
        ))
        connection.execute(text(
            "INSERT INTO repositories (id, owner, name, created_at) "
            "VALUES (1, 'Owner', 'Repo', '2026-01-01 00:00:00')"
        ))

    init_db(engine)

    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("repositories")}
    assert {"full_name", "default_branch", "last_analyzed_at"} <= columns
    with engine.connect() as connection:
        row = connection.execute(text(
            "SELECT full_name, default_branch, last_analyzed_at "
            "FROM repositories WHERE id = 1"
        )).one()
    assert row.full_name == "owner/repo"
    assert row.default_branch == "main"
    assert row.last_analyzed_at is None
    assert any(
        index.get("unique") and index.get("column_names") == ["full_name"]
        for index in inspector.get_indexes("repositories")
    )
    engine.dispose()


def test_init_db_migrates_contributor_feature_impacts(tmp_path):
    engine = create_engine_from_url(f"sqlite:///{tmp_path / 'legacy_scores.db'}")
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE contributor_scores (id INTEGER PRIMARY KEY)"
        ))

    init_db(engine)

    columns = {
        column["name"]
        for column in inspect(engine).get_columns("contributor_scores")
    }
    assert "feature_impacts" in columns
    engine.dispose()


def test_utc_datetime_requires_tz_and_round_trips(tmp_path):
    factory, engine = _session(tmp_path)
    with pytest.raises(ValueError):
        UTCDateTime().process_bind_param(datetime.now(), None)
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with factory() as session:
        repo = crud.get_or_create_repository(session, "Owner", "Repo")
        analysis = crud.create_analysis(session, repo.id, "a" * 40, {"x": 1}, "b" * 64, "1")
        analysis.created_at = now
        session.commit()
        loaded = session.get(Analysis, analysis.id)
        assert loaded.created_at.tzinfo is not None
        assert loaded.created_at.utcoffset() == timezone.utc.utcoffset(now)
    engine.dispose()


def test_cascade_and_unique_constraints(tmp_path):
    factory, engine = _session(tmp_path)
    with factory() as session:
        repo = crud.get_or_create_repository(session, "Owner", "Repo")
        analysis = crud.create_analysis(session, repo.id, "a" * 40, {}, "b" * 64, "1")
        session.add_all([
            ContributorScore(
                analysis_id=analysis.id, author_key="a", display_name="A",
                display_email="a@example.com", rank=1, score=1, base_score=1,
                share_of_team=100, penalty_multiplier=1, commits=1,
                credited_lines=1, surviving_lines=1, signals={}, notes=[],
                feature_impacts=[{"feature": "work_score", "label": "Work Signal", "impact": 1.0}],
            ),
            AnomalyRow(
                analysis_id=analysis.id, author_key="a", display_name="A",
                kind="x", severity="info", message="x", evidence={},
                penalty_multiplier=1,
            ),
            CommitRow(
                analysis_id=analysis.id, hash="c" * 40, author_key="a",
                authored_at=datetime.now(timezone.utc), meaningful_added=1,
                meaningful_credited=1, is_trivial=False, is_merge=False,
                is_bulk=False,
            ),
        ])
        session.commit()
        score = session.scalar(
            select(ContributorScore).where(ContributorScore.author_key == "a")
        )
        assert score.feature_impacts == [
            {"feature": "work_score", "label": "Work Signal", "impact": 1.0}
        ]
        session.delete(analysis)
        session.commit()
        assert session.scalar(select(ContributorScore).where(ContributorScore.author_key == "a")) is None
        with pytest.raises(IntegrityError):
            session.add(Repository(owner="Owner", name="Repo", full_name="owner/repo", created_at=datetime.now(timezone.utc)))
            session.commit()
    engine.dispose()
