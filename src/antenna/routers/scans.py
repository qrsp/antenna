from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

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


@page_router.post("/scans")
def create_scan_form(request: Request):
    request.app.state.scanner.start(force=False, limit_accounts=None)
    return RedirectResponse(url="/", status_code=303)


@page_router.post("/scans/force")
def create_force_scan_form(request: Request):
    request.app.state.scanner.start(force=True, limit_accounts=None)
    return RedirectResponse(url="/", status_code=303)
