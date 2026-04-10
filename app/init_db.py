from sqlalchemy import inspect, text
from sqlalchemy.schema import Column

from app.database import Base, engine

# Ensure model metadata is registered before create_all.
from app import models  # noqa: F401


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


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_sqlite_schema_compatibility()


if __name__ == "__main__":
    init_db()
    print("Database schema created/verified.")
