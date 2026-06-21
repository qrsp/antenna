from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import RedirectResponse

from antenna.schemas import ScanRequest, ScanResponse


router = APIRouter(prefix="/api/scans", tags=["scans"])


@router.post("", response_model=ScanResponse)
def create_scan(payload: ScanRequest, request: Request, background_tasks: BackgroundTasks) -> ScanResponse:
    scanner = request.app.state.scanner
    # Run synchronously for now so API callers immediately receive the final
    # scan status. The service itself is isolated and can move to a worker later.
    result = scanner.run(force=payload.force, limit_accounts=payload.limit_accounts)
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


@page_router.post("/scans")
def create_scan_form(request: Request):
    request.app.state.scanner.run(force=False, limit_accounts=None)
    return RedirectResponse(url="/", status_code=303)
