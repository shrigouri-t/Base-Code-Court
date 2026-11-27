"""SQLAlchemy engine, types, and session helpers."""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, Engine, event, create_engine, inspect, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON, TypeDecorator
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    """Declarative model base."""


JSONType = JSON().with_variant(JSONB(), "postgresql")


class UTCDateTime(TypeDecorator[datetime]):
    """A timezone-aware UTC datetime database type."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("UTCDateTime requires a timezone-aware datetime")
        return value.astimezone(timezone.utc)

    def process_result_value(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def create_engine_from_url(url: str) -> Engine:
    """Create a SQLite or PostgreSQL engine with safe defaults."""
    kwargs: dict[str, Any] = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" in url:
            kwargs["poolclass"] = StaticPool
    else:
        kwargs["pool_pre_ping"] = True
    engine = create_engine(url, **kwargs)
    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _enable_foreign_keys(dbapi_connection: Any, _: Any) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(engine)
    _migrate_repository_columns(engine)
    _migrate_contributor_score_columns(engine)


def _migrate_contributor_score_columns(engine: Engine) -> None:
    """Add nullable model-attribution data to existing contributor score tables."""
    inspector = inspect(engine)
    if not inspector.has_table("contributor_scores"):
        return

    columns = {column["name"] for column in inspector.get_columns("contributor_scores")}
    if "feature_impacts" in columns:
        return

    column_type = "JSONB" if engine.dialect.name == "postgresql" else "JSON"
    with engine.begin() as connection:
        connection.execute(text(
            f"ALTER TABLE contributor_scores ADD COLUMN feature_impacts {column_type}"
        ))


def _migrate_repository_columns(engine: Engine) -> None:
    """Add repository metadata columns missing from older databases."""
    inspector = inspect(engine)
    if not inspector.has_table("repositories"):
        return

    columns = {column["name"] for column in inspector.get_columns("repositories")}
    column_types = {
        "default_branch": "VARCHAR(200)",
        "full_name": "VARCHAR(201)",
        "last_analyzed_at": (
            "TIMESTAMP WITH TIME ZONE"
            if engine.dialect.name == "postgresql"
            else "DATETIME"
        ),
    }

    with engine.begin() as connection:
        for name, column_type in column_types.items():
            if name not in columns:
                connection.execute(
                    text(f"ALTER TABLE repositories ADD COLUMN {name} {column_type}")
                )

        connection.execute(text(
            "UPDATE repositories SET default_branch = 'main' "
            "WHERE default_branch IS NULL OR default_branch = ''"
        ))
        connection.execute(text(
            "UPDATE repositories SET full_name = lower(owner || '/' || name) "
            "WHERE full_name IS NULL OR full_name = ''"
        ))

        duplicate_names = connection.execute(text(
            "SELECT count(*) FROM ("
            "SELECT full_name FROM repositories "
            "GROUP BY full_name HAVING count(*) > 1"
            ") AS duplicate_repositories"
        )).scalar_one()
        if duplicate_names:
            raise RuntimeError(
                "Cannot migrate repository metadata: duplicate full_name values exist"
            )

        if engine.dialect.name == "postgresql":
            connection.execute(text(
                "ALTER TABLE repositories ALTER COLUMN default_branch SET NOT NULL"
            ))
            connection.execute(text(
                "ALTER TABLE repositories ALTER COLUMN full_name SET NOT NULL"
            ))
            for name in ("github_repo_id", "url"):
                if name in columns:
                    connection.execute(text(
                        f"ALTER TABLE repositories ALTER COLUMN {name} DROP NOT NULL"
                    ))

        indexes = inspect(connection).get_indexes("repositories")
        unique_constraints = inspect(connection).get_unique_constraints("repositories")
        has_unique_full_name = any(
            index.get("unique")
            and index.get("column_names") == ["full_name"]
            for index in indexes
        ) or any(
            constraint.get("column_names") == ["full_name"]
            for constraint in unique_constraints
        )
        if not has_unique_full_name:
            connection.execute(text(
                "CREATE UNIQUE INDEX ix_repositories_full_name "
                "ON repositories (full_name)"
            ))


def get_db(session_factory: sessionmaker[Session]):
    """Yield a request-scoped database session."""
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
