from __future__ import annotations

from urllib.parse import unquote

from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse

from antenna.models import VALID_PROCESS
from antenna.schemas import BulkProcessUpdateRequest, ProcessUpdateRequest, VideoResponse


router = APIRouter(tags=["videos"])


def _video_response(row: dict) -> VideoResponse:
    return VideoResponse(
        url=row["url"],
        video_id=row["video_id"],
        title=row["title"],
        channel_id=row["channel_id"],
        channel_name=row["channel_name"],
        start_at=row["start_at"],
        media_type=row["media_type"],
        status=row["status"],
        process=row["process"],
        thumbnail_path=row["thumbnail_path"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


@router.get("/api/videos", response_model=list[VideoResponse])
def api_list_videos(request: Request, process: str = Query("uncheck")) -> list[VideoResponse]:
    if process not in VALID_PROCESS:
        raise HTTPException(status_code=400, detail="process must be checked or uncheck")
    return [_video_response(row) for row in request.app.state.review.list_videos(process)]


@router.patch("/api/videos/{url:path}/process")
def api_update_video_process(url: str, payload: ProcessUpdateRequest, request: Request):
    count = request.app.state.review.update_process([unquote(url)], payload.process)
    if count == 0:
        raise HTTPException(status_code=404, detail="video not found")
    return {"updated": count}


@router.patch("/api/videos/process")
def api_bulk_update_process(payload: BulkProcessUpdateRequest, request: Request):
    count = request.app.state.review.update_process(payload.urls, payload.process)
    return {"updated": count}


@router.get("/videos")
def videos_page(request: Request, process: str = Query("uncheck")):
    if process not in VALID_PROCESS:
        raise HTTPException(status_code=400, detail="process must be checked or uncheck")
    rows = request.app.state.review.list_videos(process)
    return request.app.state.templates.TemplateResponse(
        request,
        "videos.html",
        {"videos": rows, "process": process},
    )


@router.post("/videos/process")
def update_video_process_form(
    request: Request,
    process: str = Form(...),
    urls: list[str] | None = Form(default=None),
):
    if process not in VALID_PROCESS:
        raise HTTPException(status_code=400, detail="process must be checked or uncheck")
    request.app.state.review.update_process(urls or [], process)
    return RedirectResponse(url=f"/videos?process={process}", status_code=303)
