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
def api_list_videos(
    request: Request,
    process: str = Query("uncheck"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
) -> list[VideoResponse]:
    if process not in VALID_PROCESS:
        raise HTTPException(status_code=400, detail="process must be checked or uncheck")
    offset = (page - 1) * per_page
    return [_video_response(row) for row in request.app.state.review.list_videos(process, limit=per_page, offset=offset)]


@router.get("/api/videos/counts")
def api_video_counts(request: Request):
    return {
        "uncheck": request.app.state.db.count_videos("uncheck"),
        "checked": request.app.state.db.count_videos("checked"),
    }


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
def videos_page(
    request: Request,
    process: str = Query("uncheck"),
    page: int = Query(1, ge=1),
):
    if process not in VALID_PROCESS:
        raise HTTPException(status_code=400, detail="process must be checked or uncheck")
    per_page = 20
    offset = (page - 1) * per_page
    rows = request.app.state.review.list_videos(process, limit=per_page, offset=offset)
    total_count = request.app.state.db.count_videos(process)
    total_pages = max(1, (total_count + per_page - 1) // per_page)
    return request.app.state.templates.TemplateResponse(
        request,
        "videos.html",
        {
            "videos": rows,
            "process": process,
            "page": page,
            "per_page": per_page,
            "total_count": total_count,
            "total_pages": total_pages,
        },
    )


@router.post("/videos/process")
def update_video_process_form(
    request: Request,
    process: str = Form(...),
    return_process: str = Form("uncheck"),
    urls: list[str] | None = Form(default=None),
):
    if process not in VALID_PROCESS:
        raise HTTPException(status_code=400, detail="process must be checked or uncheck")
    if return_process not in VALID_PROCESS:
        raise HTTPException(status_code=400, detail="return_process must be checked or uncheck")
    request.app.state.review.update_process(urls or [], process)
    return RedirectResponse(url=f"/videos?process={return_process}", status_code=303)


@router.post("/videos/check-all")
def check_all_unchecked(request: Request):
    request.app.state.review.update_all("uncheck", "checked")
    return RedirectResponse(url="/videos?process=uncheck", status_code=303)
