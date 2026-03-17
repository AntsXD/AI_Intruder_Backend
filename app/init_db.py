from app.database import Base, engine

# Ensure model metadata is registered before create_all.
from app import models  # noqa: F401


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    init_db()
    print("Database schema created/verified.")
