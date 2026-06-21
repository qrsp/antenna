from __future__ import annotations

from urllib.parse import unquote

from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse

from antenna.models import LIBRARY_ARCHIVED, LIBRARY_NEW, VALID_LIBRARY_STATES
from antenna.schemas import BulkLibraryStateUpdateRequest, LibraryStateUpdateRequest, VideoResponse

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
        library_state=row["library_state"],
        thumbnail_path=row["thumbnail_path"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


@router.get("/api/videos", response_model=list[VideoResponse])
def api_list_videos(
    request: Request,
    state: str = Query(LIBRARY_NEW),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
) -> list[VideoResponse]:
    if state not in VALID_LIBRARY_STATES:
        raise HTTPException(status_code=400, detail="state must be new or archived")
    offset = (page - 1) * per_page
    return [_video_response(row) for row in request.app.state.library.list_videos(state, limit=per_page, offset=offset)]


@router.get("/api/videos/counts")
def api_video_counts(request: Request):
    return {
        "new": request.app.state.db.count_videos(LIBRARY_NEW),
        "archived": request.app.state.db.count_videos(LIBRARY_ARCHIVED),
    }


@router.patch("/api/videos/{url:path}/state")
def api_update_video_state(url: str, payload: LibraryStateUpdateRequest, request: Request):
    count = request.app.state.library.update_state([unquote(url)], payload.state)
    if count == 0:
        raise HTTPException(status_code=404, detail="video not found")
    return {"updated": count}


@router.patch("/api/videos/state")
def api_bulk_update_state(payload: BulkLibraryStateUpdateRequest, request: Request):
    count = request.app.state.library.update_state(payload.urls, payload.state)
    return {"updated": count}


@router.get("/videos")
def videos_page(
    request: Request,
    state: str = Query(LIBRARY_NEW),
    page: int = Query(1, ge=1),
):
    if state not in VALID_LIBRARY_STATES:
        raise HTTPException(status_code=400, detail="state must be new or archived")
    per_page = 20
    offset = (page - 1) * per_page
    rows = request.app.state.library.list_videos(state, limit=per_page, offset=offset)
    total_count = request.app.state.db.count_videos(state)
    total_pages = max(1, (total_count + per_page - 1) // per_page)
    return request.app.state.templates.TemplateResponse(
        request,
        "videos.html",
        {
            "videos": rows,
            "state": state,
            "page": page,
            "per_page": per_page,
            "total_count": total_count,
            "total_pages": total_pages,
        },
    )


@router.post("/videos/state")
def update_video_state_form(
    request: Request,
    state: str = Form(...),
    return_state: str = Form(LIBRARY_NEW),
    urls: list[str] | None = Form(default=None),
):
    if state not in VALID_LIBRARY_STATES:
        raise HTTPException(status_code=400, detail="state must be new or archived")
    if return_state not in VALID_LIBRARY_STATES:
        raise HTTPException(status_code=400, detail="return_state must be new or archived")
    request.app.state.library.update_state(urls or [], state)
    return RedirectResponse(url=f"/videos?state={return_state}", status_code=303)


@router.post("/videos/archive-all")
def archive_all_new(request: Request):
    request.app.state.library.update_all(LIBRARY_NEW, LIBRARY_ARCHIVED)
    return RedirectResponse(url="/videos?state=new", status_code=303)
