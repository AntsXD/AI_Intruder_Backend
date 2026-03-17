import base64
import os
import shutil
import uuid
from pathlib import Path

import aiofiles
from fastapi import HTTPException, UploadFile, status

from app.config import settings

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_BYTES = 5 * 1024 * 1024


def ensure_storage_dirs() -> None:
    settings.storage_root_path.mkdir(parents=True, exist_ok=True)
    (settings.storage_root_path / "persons").mkdir(parents=True, exist_ok=True)
    (settings.storage_root_path / "events").mkdir(parents=True, exist_ok=True)


def _safe_ext(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported file type")
    return ext


def to_storage_relative(path: str) -> str:
    full = Path(path).resolve()
    root = settings.storage_root_path.resolve()
    try:
        return str(full.relative_to(root)).replace("\\", "/")
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid storage path")


async def save_person_photo(user_id: int, property_id: int, person_id: int, file: UploadFile) -> str:
    ensure_storage_dirs()
    ext = _safe_ext(file.filename or "")

    content = await file.read()
    if len(content) > MAX_BYTES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File too large")

    folder = settings.storage_root_path / "persons" / str(user_id) / str(property_id) / str(person_id)
    folder.mkdir(parents=True, exist_ok=True)

    name = f"{uuid.uuid4().hex}{ext}"
    full_path = folder / name
    async with aiofiles.open(full_path, "wb") as target:
        await target.write(content)

    return str(full_path)


async def save_event_snapshot_from_base64(property_id: int, payload: str) -> str:
    ensure_storage_dirs()

    try:
        data = base64.b64decode(payload, validate=True)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid snapshot payload") from exc

    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Snapshot too large")

    folder = settings.storage_root_path / "events" / str(property_id)
    folder.mkdir(parents=True, exist_ok=True)

    name = f"{uuid.uuid4().hex}.jpg"
    full_path = folder / name
    async with aiofiles.open(full_path, "wb") as target:
        await target.write(data)

    return str(full_path)


def remove_file_if_exists(path: str | None) -> None:
    if path and os.path.exists(path):
        os.remove(path)


def remove_dir_if_exists(path: Path) -> None:
    if path.exists() and path.is_dir():
        shutil.rmtree(path)
