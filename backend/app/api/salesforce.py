"""
/api/salesforce/push-lead — Push an enriched RIA lead to Salesforce CRM.

Uses the OAuth 2.0 Refresh Token flow:
  1. Exchange refresh token → fresh access token
  2. POST Lead to /services/data/v59.0/sobjects/Lead

Required Railway env vars:
  SALESFORCE_CLIENT_ID        — Connected App consumer key
  SALESFORCE_CLIENT_SECRET    — Connected App consumer secret
  SALESFORCE_REFRESH_TOKEN    — Long-lived token from initial OAuth handshake
  SALESFORCE_INSTANCE_URL     — e.g. https://myorg.my.salesforce.com

One-time setup:
  Run the OAuth web server flow once (via Salesforce CLI or postman), copy the
  refresh_token from the response, store it in Railway as SALESFORCE_REFRESH_TOKEN.
  The token never expires unless revoked — no re-auth needed.
"""

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import settings

router = APIRouter(prefix="/api/salesforce")

_SF_TOKEN_URL = "https://login.salesforce.com/services/oauth2/token"
_SF_API_VERSION = "v59.0"


class LeadPayload(BaseModel):
    firm_name: str
    crd_number: str
    aum_fmt: str | None = None
    city: str | None = None
    state: str | None = None
    priority_label: str | None = None
    anchor_text: str | None = None
    signal_bullets: list[str] = []


def _not_configured() -> bool:
    return not all([
        settings.salesforce_client_id,
        settings.salesforce_client_secret,
        settings.salesforce_refresh_token,
        settings.salesforce_instance_url,
    ])


async def _get_access_token() -> str:
    """Exchange refresh token for a short-lived access token."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(_SF_TOKEN_URL, data={
            "grant_type": "refresh_token",
            "client_id": settings.salesforce_client_id,
            "client_secret": settings.salesforce_client_secret,
            "refresh_token": settings.salesforce_refresh_token,
        })
        if resp.status_code != 200:
            raise HTTPException(
                status_code=502,
                detail=f"Salesforce OAuth failed: {resp.text[:200]}"
            )
        return resp.json()["access_token"]


def _build_description(payload: LeadPayload) -> str:
    lines = []
    if payload.anchor_text:
        lines.append(f"Outcome: {payload.anchor_text}")
    if payload.priority_label:
        lines.append(f"Priority: {payload.priority_label}")
    if payload.aum_fmt:
        lines.append(f"AUM: {payload.aum_fmt}")
    if payload.crd_number:
        lines.append(f"CRD: {payload.crd_number}")
    if payload.signal_bullets:
        lines.append("\nSignals:")
        for b in payload.signal_bullets[:3]:
            lines.append(f"  • {b}")
    lines.append("\nSource: pcIQ — public SEC data (Form ADV · EDGAR · 13F)")
    return "\n".join(lines)


@router.post("/push-lead")
async def push_lead(payload: LeadPayload) -> dict:
    """
    Push an enriched advisor as a Lead to Salesforce.

    Returns {"status": "created", "sf_id": "..."} on success.
    Returns {"status": "not_configured"} when Salesforce env vars are not set.
    """
    if _not_configured():
        return {
            "status": "not_configured",
            "message": "Salesforce credentials not set. Add SALESFORCE_CLIENT_ID, "
                       "SALESFORCE_CLIENT_SECRET, SALESFORCE_REFRESH_TOKEN, and "
                       "SALESFORCE_INSTANCE_URL to Railway environment variables.",
        }

    access_token = await _get_access_token()

    # Split firm_name into FirstName / LastName for Salesforce Lead model
    # Salesforce requires LastName — use firm name as LastName, "RIA Contact" as FirstName
    lead = {
        "FirstName": "RIA Contact",
        "LastName": payload.firm_name,
        "Company": payload.firm_name,
        "State": payload.state or "",
        "City": payload.city or "",
        "LeadSource": "pcIQ",
        "Description": _build_description(payload),
        # Custom fields — add to your Salesforce Lead object if needed:
        # "pcIQ_CRD__c": payload.crd_number,
        # "pcIQ_AUM__c": payload.aum_fmt,
        # "pcIQ_Priority__c": payload.priority_label,
    }

    url = f"{settings.salesforce_instance_url}/services/data/{_SF_API_VERSION}/sobjects/Lead"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(url, json=lead, headers=headers)

    if resp.status_code in (200, 201):
        data = resp.json()
        return {"status": "created", "sf_id": data.get("id", "")}

    # Duplicate detected — Salesforce returns 400 with errorCode DUPLICATE_VALUE
    if resp.status_code == 400:
        errors = resp.json() if resp.content else []
        if isinstance(errors, list) and any(
            e.get("errorCode") == "DUPLICATE_VALUE" for e in errors
        ):
            return {"status": "duplicate", "message": "Lead already exists in Salesforce."}

    raise HTTPException(
        status_code=502,
        detail=f"Salesforce API error {resp.status_code}: {resp.text[:300]}"
    )
