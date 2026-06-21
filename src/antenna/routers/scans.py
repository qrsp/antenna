from __future__ import annotations

from datetime import UTC

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from antenna.db import db_to_dt, utcnow
from antenna.schemas import ScanRequest, ScanResponse
from antenna.services.scan_service import ScanAlreadyRunningError

router = APIRouter(prefix="/api/scans", tags=["scans"])


@router.post("", response_model=ScanResponse)
def create_scan(payload: ScanRequest, request: Request) -> ScanResponse:
    scanner = request.app.state.scanner
    _validate_limit_accounts(payload.limit_accounts, request)
    try:
        result = scanner.start(force=payload.force, limit_accounts=payload.limit_accounts)
    except ScanAlreadyRunningError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "scan_in_progress",
                "message": "A scan is already running.",
                "scan": exc.running_scan,
            },
        ) from exc
    return ScanResponse(**result)


@router.post("/cancel", response_model=ScanResponse)
def cancel_scan(request: Request) -> ScanResponse:
    result = request.app.state.scanner.cancel()
    if result is None:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "no_scan_running",
                "message": "No scan is currently running.",
            },
        )
    return ScanResponse(**result)


@router.get("/status")
def scan_status(request: Request):
    latest = request.app.state.db.get_latest_scan()
    return {
        "running": request.app.state.scanner.is_running(),
        "latest": latest,
    }


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
        parsed = parsed.replace(tzinfo=UTC)
    return max(0, (utcnow() - parsed).days)


ACCOUNT_SORT_OPTIONS = {
    "user_screen_name": "Account",
    "last_scan_at": "Last scan",
    "last_tweet_at": "Last tweet",
    "last_tweet_age_days": "Tweet age",
    "last_status": "Status",
    "last_status_id": "Latest status ID",
    "next_scan_at": "Next account scan",
    "last_error": "Error",
}
ACCOUNT_SORT_DIRECTIONS = {"asc", "desc"}


def _validate_limit_accounts(limit_accounts: list[str] | None, request: Request) -> None:
    if not limit_accounts:
        return
    configured = set(request.app.state.settings.lists.follow)
    unknown = [username for username in limit_accounts if username not in configured]
    if unknown:
        raise HTTPException(status_code=400, detail="account must be in the follow list")


def _normalized_sort(sort: str, direction: str) -> tuple[str, str]:
    if sort not in ACCOUNT_SORT_OPTIONS:
        sort = "user_screen_name"
    if direction not in ACCOUNT_SORT_DIRECTIONS:
        direction = "asc"
    return sort, direction


def _sort_datetime(value):
    if value is None:
        return None
    if isinstance(value, str):
        value = db_to_dt(value)
    if value is not None and value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value


def _account_sort_value(row: dict, sort: str):
    if sort == "user_screen_name":
        return row["user_screen_name"].casefold()
    if sort in {"last_scan_at", "last_tweet_at"}:
        return _sort_datetime(row.get(sort))
    if sort == "last_tweet_age_days":
        return row.get(sort)
    if sort == "last_status":
        return f"{row.get('last_status') or ''} {row.get('schedule_reason') or ''}".casefold()
    if sort == "last_status_id":
        status_id = row.get("last_status_id")
        return status_id.casefold() if status_id else None
    if sort == "next_scan_at":
        if row.get("can_scan") and row.get("next_scan_at") is None:
            return db_to_dt("0001-01-01T00:00:00+00:00")
        return _sort_datetime(row.get("next_scan_at"))
    if sort == "last_error":
        return (row.get("last_error") or "").casefold()
    return row["user_screen_name"].casefold()


def _sort_accounts(rows: list[dict], sort: str, direction: str) -> list[dict]:
    def has_value(row: dict) -> bool:
        value = _account_sort_value(row, sort)
        return value is not None and value != ""

    populated = [row for row in rows if has_value(row)]
    empty = [row for row in rows if not has_value(row)]
    populated.sort(
        key=lambda row: (_account_sort_value(row, sort), row["user_screen_name"].casefold()),
        reverse=direction == "desc",
    )
    empty.sort(key=lambda row: row["user_screen_name"].casefold())
    return populated + empty


@page_router.post("/scans")
def create_scan_form(request: Request):
    try:
        request.app.state.scanner.start(force=False, limit_accounts=None)
    except ScanAlreadyRunningError:
        return RedirectResponse(url="/?scan_error=in_progress", status_code=303)
    return RedirectResponse(url="/", status_code=303)


@page_router.post("/scans/force")
def create_force_scan_form(request: Request):
    try:
        request.app.state.scanner.start(force=True, limit_accounts=None)
    except ScanAlreadyRunningError:
        return RedirectResponse(url="/?scan_error=in_progress", status_code=303)
    return RedirectResponse(url="/", status_code=303)


@page_router.post("/scans/cancel")
def cancel_scan_form(request: Request):
    request.app.state.scanner.cancel()
    return RedirectResponse(url="/", status_code=303)


@page_router.get("/accounts")
def account_scan_states_page(request: Request, sort: str = "user_screen_name", direction: str = "asc"):
    sort, direction = _normalized_sort(sort, direction)
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
            "last_status_id": None,
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
    rows = _sort_accounts(rows, sort, direction)

    return request.app.state.templates.TemplateResponse(
        request,
        "accounts.html",
        {
            "accounts": rows,
            "sort": sort,
            "direction": direction,
            "sort_options": ACCOUNT_SORT_OPTIONS,
            "scan_running": request.app.state.scanner.is_running(),
        },
    )


@page_router.post("/accounts/scan")
def scan_single_account_form(
    request: Request,
    username: str = Form(...),
):
    username = username.strip()
    if username not in request.app.state.settings.lists.follow:
        raise HTTPException(status_code=400, detail="account must be in the follow list")
    try:
        request.app.state.scanner.start(force=True, limit_accounts=[username])
    except ScanAlreadyRunningError:
        return RedirectResponse(url="/accounts?scan_error=in_progress", status_code=303)
    return RedirectResponse(url="/", status_code=303)
