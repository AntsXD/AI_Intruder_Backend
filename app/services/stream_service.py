from urllib.parse import urlparse

from fastapi import HTTPException, status

from app.models.entities import StreamType


def validate_stream_url_for_type(source_url: str, stream_type: StreamType) -> None:
    parsed = urlparse(source_url)
    if parsed.scheme not in {"http", "https"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only http/https stream URLs are supported")

    if stream_type == StreamType.HTTP_PROXY and not parsed.netloc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid proxy stream URL")
