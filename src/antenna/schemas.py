from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

LibraryState = Literal["archived", "new"]


class HealthResponse(BaseModel):
    status: str
    database: str
    version: str


class ScanRequest(BaseModel):
    force: bool = False
    limit_accounts: list[str] | None = None


class ScanResponse(BaseModel):
    id: int
    status: str
    message: str | None = None
    stats: dict = Field(default_factory=dict)


class LibraryStateUpdateRequest(BaseModel):
    state: LibraryState


class BulkLibraryStateUpdateRequest(BaseModel):
    urls: list[str]
    state: LibraryState


class VideoResponse(BaseModel):
    url: str
    video_id: str
    title: str | None
    channel_id: str | None
    channel_name: str | None
    start_at: str | None
    media_type: str | None
    status: str
    library_state: LibraryState
    thumbnail_path: str | None
    created_at: str
    updated_at: str
