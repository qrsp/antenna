from __future__ import annotations

from datetime import timezone

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from antenna.db import db_to_dt, utcnow
from antenna.schemas import ScanRequest, ScanResponse


router = APIRouter(prefix="/api/scans", tags=["scans"])


@router.post("", response_model=ScanResponse)
def create_scan(payload: ScanRequest, request: Request) -> ScanResponse:
    scanner = request.app.state.scanner
    result = scanner.start(force=payload.force, limit_accounts=payload.limit_accounts)
    return ScanResponse(**result)


@router.get("/latest")
def latest_scan(request: Request):
    result = request.app.state.db.get_latest_scan()
    if result is None:
        raise HTTPException(status_code=404, detail="no scans found")
    return result


@router.get("/{scan_id}")
def get_scan(scan_id: int, request: Request):
    result = request.app.state.db.get_scan(scan_id)
    if result is None:
        raise HTTPException(status_code=404, detail="scan not found")
    return result


page_router = APIRouter(tags=["scans"])


def _days_since(value: str | None) -> int | None:
    parsed = db_to_dt(value)
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return max(0, (utcnow() - parsed).days)


@page_router.post("/scans")
def create_scan_form(request: Request):
    request.app.state.scanner.start(force=False, limit_accounts=None)
    return RedirectResponse(url="/", status_code=303)


@page_router.post("/scans/force")
def create_force_scan_form(request: Request):
    request.app.state.scanner.start(force=True, limit_accounts=None)
    return RedirectResponse(url="/", status_code=303)


@page_router.get("/accounts")
def account_scan_states_page(request: Request):
    settings = request.app.state.settings
    scheduler = request.app.state.scheduler
    states = request.app.state.db.list_account_states()
    states_by_username = {state["user_screen_name"]: state for state in states}
    configured_accounts = set(settings.lists.follow)
    usernames = sorted(
        configured_accounts | set(states_by_username),
        key=str.casefold,
    )
    rows = []
    for username in usernames:
        state = states_by_username.get(username) or {
            "user_screen_name": username,
            "last_scan_at": None,
            "last_tweet_at": None,
            "last_status": "never_scanned",
            "last_error": None,
            "updated_at": None,
        }
        if username in configured_accounts:
            decision = scheduler.decide_account(username)
            state["schedule_reason"] = decision.reason
            state["next_scan_at"] = None if decision.should_scan else decision.deferred_until
            state["can_scan"] = True
        else:
            state["schedule_reason"] = "not_in_follow_list"
            state["next_scan_at"] = None
            state["can_scan"] = False
        state["last_tweet_age_days"] = _days_since(state.get("last_tweet_at"))
        rows.append(state)

    return request.app.state.templates.TemplateResponse(
        request,
        "accounts.html",
        {"accounts": rows},
    )


@page_router.post("/accounts/scan")
def scan_single_account_form(request: Request, username: str = Form(...)):
    username = username.strip()
    if username not in request.app.state.settings.lists.follow:
        raise HTTPException(status_code=400, detail="account must be in the follow list")
    request.app.state.scanner.start(force=True, limit_accounts=[username])
    return RedirectResponse(url="/accounts", status_code=303)
