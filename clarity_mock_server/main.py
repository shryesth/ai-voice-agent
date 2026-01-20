"""Mock FastAPI server for client visit verification endpoints."""

from __future__ import annotations

import json
import math
from datetime import date, datetime
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.security import APIKeyHeader

from models import (
    PaginatedResponse,
    VerificationStatus,
    VerificationSubjectInput,
    VerificationSubjectOutput,
)

# Hardcoded API key for mock authentication
VALID_API_KEY = "mock-api-key-12345"

api_key_header = APIKeyHeader(
    name="X-API-Key",
    auto_error=False,
    description="API key for authentication",
)


def verify_api_key(api_key: str | None = Depends(api_key_header)) -> str:
    """Verify the API key from the X-API-Key header."""
    if api_key is None:
        raise HTTPException(
            status_code=401,
            detail="Missing API key. Provide X-API-Key header.",
        )
    if api_key != VALID_API_KEY:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key",
        )
    return api_key


app = FastAPI(
    title="Client Visit Verification Mock API",
    description="Mock server for testing client visit verification endpoints",
    version="1.0.0",
)

DATA_DIR = Path(__file__).parent / "data"
VERIFICATIONS_FILE = DATA_DIR / "verifications.json"
UPDATES_FILE = DATA_DIR / "updates.json"


def load_verifications() -> list[dict]:
    """Load verification data from JSON file."""
    with open(VERIFICATIONS_FILE) as f:
        return json.load(f)


def save_verifications(data: list[dict]) -> None:
    """Save verification data to JSON file."""
    with open(VERIFICATIONS_FILE, "w") as f:
        json.dump(data, f, indent=2, default=str)


def load_updates() -> list[dict]:
    """Load updates log from JSON file."""
    with open(UPDATES_FILE) as f:
        return json.load(f)


def save_updates(data: list[dict]) -> None:
    """Save updates log to JSON file."""
    with open(UPDATES_FILE, "w") as f:
        json.dump(data, f, indent=2, default=str)


def log_update(verification_id: int, changes: dict) -> None:
    """Log an update to the updates file."""
    updates = load_updates()
    updates.append(
        {
            "id": verification_id,
            "timestamp": datetime.now().isoformat(),
            "changes": changes,
        }
    )
    save_updates(updates)


@app.get(
    "/api/v1/hmis/client-visits/verification",
    response_model=PaginatedResponse[VerificationSubjectOutput],
    tags=["hmis"],
    summary="Get available client visits for verification",
)
def get_available_client_visit_for_verification(
    _api_key: str = Depends(verify_api_key),
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[
        int, Query(ge=1, alias="pageSize", description="Number of elements per page")
    ] = 50,
    date_from: Annotated[
        date | None,
        Query(alias="dateFrom", description="Filter by visit date (inclusive)"),
    ] = None,
    date_to: Annotated[
        date | None,
        Query(alias="dateTo", description="Filter by visit date (inclusive)"),
    ] = None,
) -> PaginatedResponse[VerificationSubjectOutput]:
    """Get paginated list of client visits available for verification.

    Returns visits with IN_PROGRESS (1) or UNKNOWN (999) status by default.
    """
    verifications = load_verifications()

    # Filter by status (only IN_PROGRESS and UNKNOWN can be verified)
    filtered = [
        v
        for v in verifications
        if v["status"] in (VerificationStatus.IN_PROGRESS, VerificationStatus.UNKNOWN)
    ]

    # Filter by date range if provided
    if date_from:
        filtered = [
            v
            for v in filtered
            if date.fromisoformat(v["eventInfo"]["eventDate"]) >= date_from
        ]
    if date_to:
        filtered = [
            v
            for v in filtered
            if date.fromisoformat(v["eventInfo"]["eventDate"]) <= date_to
        ]

    # Calculate pagination
    total = len(filtered)
    pages = math.ceil(total / page_size) if total > 0 else 1
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    items = filtered[start_idx:end_idx]

    # Update canBeChanged based on current status
    for item in items:
        item["canBeChanged"] = VerificationStatus.can_be_updated(item["status"])

    return PaginatedResponse(
        items=[VerificationSubjectOutput(**item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
        has_next=page < pages,
        has_previous=page > 1,
    )


@app.put(
    "/api/v1/hmis/client-visits/verification/{client_visit_verification_id}",
    response_model=VerificationSubjectOutput,
    tags=["hmis"],
    summary="Update client visit verification",
)
def client_visit_verification_update(
    client_visit_verification_id: int,
    body: VerificationSubjectInput,
    _api_key: str = Depends(verify_api_key),
) -> VerificationSubjectOutput:
    """Update a client visit verification record.

    Only records with IN_PROGRESS (1) or UNKNOWN (999) status can be updated.
    """
    verifications = load_verifications()

    # Find the verification record
    record = None
    record_idx = None
    for idx, v in enumerate(verifications):
        if v["id"] == client_visit_verification_id:
            record = v
            record_idx = idx
            break

    if record is None:
        raise HTTPException(
            status_code=404,
            detail=f"Verification record with ID {client_visit_verification_id} not found",
        )

    # Check if record can be updated
    if not VerificationStatus.can_be_updated(record["status"]):
        raise HTTPException(
            status_code=400,
            detail=f"Verification record with status {record['status']} cannot be updated",
        )

    # Track changes for logging
    changes = {}

    # Apply updates
    if body.status is not None:
        changes["status"] = {"from": record["status"], "to": body.status}
        record["status"] = body.status
        record["canBeChanged"] = VerificationStatus.can_be_updated(body.status)

    if body.recording_url is not None:
        changes["recordingUrl"] = {
            "from": record["recordingUrl"],
            "to": body.recording_url,
        }
        record["recordingUrl"] = body.recording_url

    if body.is_visit_confirmed is not None:
        changes["isVisitConfirmed"] = {
            "from": record["isVisitConfirmed"],
            "to": body.is_visit_confirmed,
        }
        record["isVisitConfirmed"] = body.is_visit_confirmed

    # Save updates
    verifications[record_idx] = record
    save_verifications(verifications)

    # Log the update
    if changes:
        log_update(client_visit_verification_id, changes)

    return VerificationSubjectOutput(**record)


@app.get("/health", tags=["health"])
def health_check() -> dict:
    """Health check endpoint."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
