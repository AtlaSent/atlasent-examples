"""
AtlaSent Webhook Verification — Python / FastAPI

Demonstrates verifying an incoming AtlaSent webhook using
`assert_webhook` from the `atlasent` package. The raw request body
must be passed to the verifier before any JSON parsing.

Run:
    ATLASENT_WEBHOOK_SECRET=whsec_... uvicorn index:app --reload
"""

import json
import os

from atlasent import assert_webhook, WebhookVerificationError
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

app = FastAPI()

WEBHOOK_SECRET = os.environ.get("ATLASENT_WEBHOOK_SECRET", "")


@app.post("/webhooks/atlasent")
async def handle_webhook(request: Request) -> JSONResponse:
    """Receive and verify an AtlaSent webhook event."""
    # Read raw bytes BEFORE any parsing — the HMAC covers the wire bytes.
    body = await request.body()
    signature = request.headers.get("x-atlasent-signature", "")

    # assert_webhook raises WebhookVerificationError if the signature is
    # missing, expired, or does not match. verifyWebhook (non-raising) is
    # also available if you prefer a boolean return.
    try:
        assert_webhook(body, signature, WEBHOOK_SECRET)
    except WebhookVerificationError:
        raise HTTPException(status_code=400, detail="invalid_signature")

    # Safe to parse now — bytes are confirmed authentic.
    event = json.loads(body)
    print(f"Verified event: {event.get('type')}")

    # Acknowledge immediately; process asynchronously if needed.
    return JSONResponse({"received": True})


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"ok": True})
