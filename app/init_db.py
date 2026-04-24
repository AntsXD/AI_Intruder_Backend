from sqlalchemy import inspect, text
from sqlalchemy.schema import Column

from app.database import Base, engine

# Ensure model metadata is registered before create_all.
from app import models  # noqa: F401


def _migrate_sqlite_events_verified_intruder_nullable(connection) -> None:
    """
    Rebuild the events table so verified_intruder becomes nullable.
    SQLite cannot ALTER COLUMN nullability in place.
    """
    connection.execute(text("PRAGMA foreign_keys=OFF"))
    try:
        connection.execute(
            text(
                """
                CREATE TABLE events__new (
                    id INTEGER NOT NULL,
                    property_id INTEGER NOT NULL,
                    person_id INTEGER,
                    similarity_score FLOAT NOT NULL,
                    ai_status VARCHAR(17) NOT NULL,
                    snapshot_path VARCHAR(500) NOT NULL,
                    occurred_at DATETIME NOT NULL,
                    note TEXT,
                    verified_intruder BOOLEAN,
                    protocols_activated BOOLEAN NOT NULL,
                    distance_meters FLOAT,
                    dwell_time_seconds FLOAT,
                    expires_at DATETIME NOT NULL,
                    PRIMARY KEY (id),
                    FOREIGN KEY(property_id) REFERENCES properties (id) ON DELETE CASCADE,
                    FOREIGN KEY(person_id) REFERENCES persons (id) ON DELETE SET NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO events__new (
                    id,
                    property_id,
                    person_id,
                    similarity_score,
                    ai_status,
                    snapshot_path,
                    occurred_at,
                    note,
                    verified_intruder,
                    protocols_activated,
                    distance_meters,
                    dwell_time_seconds,
                    expires_at
                )
                SELECT
                    id,
                    property_id,
                    person_id,
                    similarity_score,
                    ai_status,
                    snapshot_path,
                    occurred_at,
                    note,
                    verified_intruder,
                    protocols_activated,
                    distance_meters,
                    dwell_time_seconds,
                    expires_at
                FROM events
                """
            )
        )
        connection.execute(text("DROP TABLE events"))
        connection.execute(text("ALTER TABLE events__new RENAME TO events"))
        connection.execute(text("CREATE INDEX ix_events_property_id ON events (property_id)"))
        connection.execute(text("CREATE INDEX ix_events_person_id ON events (person_id)"))
        connection.execute(text("CREATE INDEX ix_events_ai_status ON events (ai_status)"))
    finally:
        connection.execute(text("PRAGMA foreign_keys=ON"))


def ensure_sqlite_schema_compatibility() -> None:
    """
    For SQLite, add any missing columns from the model definitions to the database.
    This handles schema evolution on databases that predate new model columns.
    """
    if not engine.dialect.name == "sqlite":
        return

    with engine.begin() as connection:
        inspector = inspect(connection)

        for table in Base.metadata.sorted_tables:
            table_name = table.name

            if not inspector.has_table(table_name):
                continue

            existing_columns = {column["name"] for column in inspector.get_columns(table_name)}

            # Check each column in the model definition
            for model_column in table.columns:
                col_name = model_column.name

                if col_name not in existing_columns:
                    # Generate a simple ALTER TABLE ADD COLUMN statement
                    # Use the column type as a string (works for most common types)
                    col_type = str(model_column.type)
                    nullable_clause = "" if model_column.nullable else ""
                    ddl = f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type}{nullable_clause}"
                    connection.execute(text(ddl))

        events_columns = {column["name"]: column for column in inspector.get_columns("events")} if inspector.has_table("events") else {}
        verified_intruder_column = events_columns.get("verified_intruder")
        if verified_intruder_column and not verified_intruder_column.get("nullable", True):
            _migrate_sqlite_events_verified_intruder_nullable(connection)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_sqlite_schema_compatibility()


if __name__ == "__main__":
    init_db()
    print("Database schema created/verified.")
