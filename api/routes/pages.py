"""Static page routes for local MVP play/debug."""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter(tags=["pages"])


@router.get(
    "/play",
    summary="Play Page",
    description="Serve the local MVP play page.",
)
def play_page() -> FileResponse:
    page = Path(__file__).resolve().parents[1] / "static" / "play.html"
    return FileResponse(path=str(page), media_type="text/html")
