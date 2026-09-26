#!/usr/bin/env python3
"""
AtlaSent Python Human-in-the-Loop Approval Workflow

Submits an action for evaluation. If the decision is:
  - "allow"    -> prints the permit token and proceeds
  - "deny"     -> prints the reasons and exits non-zero
  - "hold"     -> creates a V1 escalation (POST /v1/escalations) and polls
                  POST /v1/escalations/:id/respond until terminal state or
                  max retries are exhausted
  - "escalate" -> prints escalation instructions and exits non-zero

V1 EvaluateResponse fields used:
  decision      – canonical lowercase: "allow" | "deny" | "hold" | "escalate"
  request_id    – stable ID present on both CP and SaaS runtimes
  permit_token  – returned when decision is "allow"; send to verify-permit
  deny_code     – machine-readable denial code (e.g. "DENY_POLICY_EXPLICIT")
  deny_reason   – human-readable denial explanation

HITL V1 API:
  POST /v1/escalations                     create escalation
  POST /v1/escalations/:id/respond         respond { decision: "approve" | "reject" }
  Terminal states: approved | rejected | timed_out

Auth: the SDK (or this raw httpx implementation) sends
      Authorization: Bearer <key>. Bad keys return HTTP 401.

Decision values are canonical lowercase: "allow" | "deny" | "hold" | "escalate".
Always compare with == "allow", never == "ALLOW".

Required env vars:
    ATLASENT_API_KEY  — your API key
    ATLASENT_API_URL  — base URL, e.g. https://api.atlasent.io/functions/v1
    ATLASENT_ORG_ID   — your organisation ID
"""

from __future__ import annotations

import os
import sys
import time
import httpx
from dotenv import load_dotenv

load_dotenv()

# ── Configuration ──────────────────────────────────────────────────────────
API_KEY = os.environ.get("ATLASENT_API_KEY")
API_URL = os.environ.get("ATLASENT_API_URL", "https://api.atlasent.io/functions/v1")
ORG_ID  = os.environ.get("ATLASENT_ORG_ID")

if not API_KEY:
    print("Error: ATLASENT_API_KEY is not set.", file=sys.stderr)
    print("       Create one at: AtlaSent console → Settings → API Keys", file=sys.stderr)
    sys.exit(1)
if not ORG_ID:
    print("Error: ATLASENT_ORG_ID is not set.", file=sys.stderr)
    print("       Find it at: AtlaSent console → Settings → Organisation", file=sys.stderr)
    sys.exit(1)

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}

# Polling config for "hold" decisions / escalation polling
POLL_INITIAL_DELAY = 2    # seconds
POLL_MAX_DELAY     = 30   # cap backoff at 30s
POLL_MAX_ATTEMPTS  = 10

# V1 escalation terminal states
ESCALATION_TERMINAL_STATES = {"approved", "rejected", "timed_out"}


# ── Evaluate ───────────────────────────────────────────────────────────────
def evaluate(actor_id: str, action_type: str, context: dict | None = None) -> dict:
    """Call POST /v1/evaluate and return the parsed JSON response.

    V1 response shape:
      {
        decision:     "allow" | "deny" | "hold" | "escalate",
        request_id:   str,   # stable ID on both CP and SaaS runtimes
        permit_token: str,   # present when decision == "allow"
        deny_code:    str,   # present when decision != "allow"
        deny_reason:  str,   # human-readable denial explanation
      }
    """
    url = f"{API_URL.rstrip('/')}/v1/evaluate"
    payload = {
        "actor_id":    actor_id,
        "action_type": action_type,
        "context":     context or {},
    }
    try:
        response = httpx.post(url, headers=HEADERS, json=payload, timeout=15)
    except httpx.RequestError as exc:
        print(f"Network error calling AtlaSent: {exc}", file=sys.stderr)
        sys.exit(1)

    _handle_http_error(response)
    return response.json()


# ── Create HITL escalation ─────────────────────────────────────────────────
def create_escalation(evaluation_id: str, context: dict | None = None) -> dict:
    """Create a HITL escalation via POST /v1/escalations.

    Returns the escalation object including its `id`.
    """
    url = f"{API_URL.rstrip('/')}/v1/escalations"
    payload: dict = {"evaluationId": evaluation_id}
    if context:
        payload["context"] = context
    try:
        response = httpx.post(url, headers=HEADERS, json=payload, timeout=15)
    except httpx.RequestError as exc:
        print(f"Network error creating escalation: {exc}", file=sys.stderr)
        sys.exit(1)
    _handle_http_error(response)
    return response.json()


# ── Poll escalation for resolution ────────────────────────────────────────
def poll_escalation(escalation_id: str) -> dict | None:
    """
    Poll POST /v1/escalations/:id/respond (GET the escalation state) using
    exponential backoff until the escalation reaches a terminal state
    (approved | rejected | timed_out), or until max attempts are reached.

    Returns the resolved escalation dict, or None on timeout.
    """
    url = f"{API_URL.rstrip('/')}/v1/escalations/{escalation_id}"
    delay = POLL_INITIAL_DELAY

    for attempt in range(1, POLL_MAX_ATTEMPTS + 1):
        print(f"  Polling escalation {escalation_id} "
              f"(attempt {attempt}/{POLL_MAX_ATTEMPTS}, "
              f"next check in {delay}s)...")
        time.sleep(delay)

        try:
            response = httpx.get(url, headers=HEADERS, timeout=15)
        except httpx.RequestError as exc:
            print(f"  Network error while polling: {exc}", file=sys.stderr)
            delay = min(delay * 2, POLL_MAX_DELAY)
            continue

        _handle_http_error(response, fatal=False)
        if response.is_error:
            delay = min(delay * 2, POLL_MAX_DELAY)
            continue

        escalation = response.json()
        state = str(escalation.get("state", "")).lower()

        if state in ESCALATION_TERMINAL_STATES:
            return escalation

        # Still pending — back off and retry
        delay = min(delay * 2, POLL_MAX_DELAY)

    return None  # timed out


# ── HTTP error helper ──────────────────────────────────────────────────────
def _handle_http_error(response: httpx.Response, fatal: bool = True) -> None:
    """Print a developer-friendly message for common HTTP errors."""
    if response.is_success:
        return

    status = response.status_code

    if status == 401:
        print("Got 401 — your ATLASENT_API_KEY may be wrong or expired.",
              file=sys.stderr)
        print("Regenerate it at: AtlaSent console → Settings → API Keys",
              file=sys.stderr)
        if fatal:
            sys.exit(1)
        return

    if status == 429:
        print("Got 429 — rate limited (100 req/min per org).", file=sys.stderr)
        print("Back off and retry after the Retry-After header duration.",
              file=sys.stderr)
        if fatal:
            sys.exit(1)
        return

    # Structured error body: { error: "snake_case_code", message: "...", status: N }
    try:
        body = response.json()
        code    = body.get("error", "unknown")
        message = body.get("message", response.text)
        print(f"API error [{code}]: {message} (HTTP {status})", file=sys.stderr)
    except Exception:
        print(f"HTTP {status}: {response.text}", file=sys.stderr)

    if fatal:
        sys.exit(1)


# ── Main ───────────────────────────────────────────────────────────────────
def main() -> None:
    actor_id    = os.environ.get("ATLASENT_AGENT",  "workflow-bot")
    action_type = os.environ.get("ATLASENT_ACTION", "records:approve")
    context = {
        "record_id":  os.environ.get("RECORD_ID", "rec_demo_001"),
        "approver":   os.environ.get("APPROVER",  "alice@example.com"),
        "reason":     "Quarterly compliance review",
    }

    print("=== AtlaSent Approval Workflow ===")
    print(f"Actor  : {actor_id}")
    print(f"Action : {action_type}")
    print(f"Context: {context}")
    print()

    result = evaluate(actor_id, action_type, context)

    # V1 EvaluateResponse fields (all snake_case)
    decision     = str(result.get("decision", "unknown")).lower()
    request_id   = result.get("request_id", "")
    permit_token = result.get("permit_token", "")   # present when decision == "allow"
    deny_code    = result.get("deny_code", "")
    deny_reason  = result.get("deny_reason", "")

    print(f"Decision      : {decision}")
    print(f"Request ID    : {request_id}")
    if deny_code:
        print(f"Deny code     : {deny_code}")
    if deny_reason:
        print(f"Deny reason   : {deny_reason}")
    if permit_token:
        print(f"Permit Token  : {permit_token}")
    print()

    if decision == "allow":
        print("Action approved. Proceeding with workflow.")
        # permit_token must be sent to verify-permit before executing the action
        print(f"[simulated] Verifying permit {permit_token}...")
        print(f"[simulated] Processing record {context['record_id']}...")
        print("Workflow complete.")
        sys.exit(0)

    if decision == "deny":
        reason_text = deny_reason or deny_code or "(no reason provided)"
        print(f"Action denied: {reason_text}", file=sys.stderr)
        sys.exit(1)

    if decision == "hold":
        if not request_id:
            print("Hold decision received but no request_id returned — cannot create escalation.",
                  file=sys.stderr)
            sys.exit(1)

        print(f"Action is on hold. Creating HITL escalation (POST /v1/escalations)...")
        escalation = create_escalation(request_id, context)
        escalation_id = escalation.get("id", "")
        if not escalation_id:
            print("Escalation created but no id returned — cannot poll.",
                  file=sys.stderr)
            sys.exit(1)
        print(f"Escalation ID : {escalation_id}")
        print(f"Polling for approval (up to {POLL_MAX_ATTEMPTS} attempts)...")

        resolved = poll_escalation(escalation_id)

        if resolved is None:
            print(f"\nTimed out after {POLL_MAX_ATTEMPTS} attempts.", file=sys.stderr)
            print("Check the AtlaSent console to approve or reject this request.",
                  file=sys.stderr)
            print(f"Escalation ID: {escalation_id}", file=sys.stderr)
            sys.exit(1)

        # Terminal states: approved | rejected | timed_out
        terminal_state = str(resolved.get("state", "unknown")).lower()
        print(f"Escalation resolved: {terminal_state}")

        if terminal_state == "approved":
            resolved_permit = resolved.get("permit_token", "")
            print("Approval received. Proceeding with workflow.")
            if resolved_permit:
                print(f"[simulated] Verifying permit {resolved_permit}...")
            print(f"[simulated] Processing record {context['record_id']}...")
            print("Workflow complete.")
            sys.exit(0)
        elif terminal_state == "timed_out":
            print(f"Escalation timed out. Halting.", file=sys.stderr)
            sys.exit(1)
        else:
            print(f"Escalation was rejected (state: {terminal_state}). Halting.",
                  file=sys.stderr)
            sys.exit(1)

    if decision == "escalate":
        reason_text = deny_reason or deny_code or "(no reason provided)"
        print("Action requires escalation.", file=sys.stderr)
        print(f"Reason    : {reason_text}", file=sys.stderr)
        print(f"Request ID: {request_id}", file=sys.stderr)
        print("Next steps:", file=sys.stderr)
        print("  1. Notify your compliance team or AtlaSent administrator.", file=sys.stderr)
        print("  2. They can review and approve in the AtlaSent console.", file=sys.stderr)
        sys.exit(2)

    print(f"Unrecognised decision value: \"{decision}\". Failing closed.", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
