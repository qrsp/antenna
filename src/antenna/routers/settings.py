from __future__ import annotations

from fastapi import APIRouter, Request


router = APIRouter(tags=["settings"])


@router.get("/settings")
def settings_page(request: Request):
    settings = request.app.state.settings
    pause_until = request.app.state.scheduler.twitter_pause_until()
    return request.app.state.templates.TemplateResponse(
        request,
        "settings.html",
        {
            "settings": settings,
            "pause_until": pause_until,
        },
    )
