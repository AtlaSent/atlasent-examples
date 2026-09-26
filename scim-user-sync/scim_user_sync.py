"""SCIM user sync example.

Demonstrates: provisioning a user, updating their active status via PATCH,
adding them to a group, then deprovisioning via DELETE.

Flow:
    scim_create_user
    -> scim_patch_user (active: False)
    -> scim_create_group
    -> scim_patch_group (add member)
    -> scim_delete_user

Requires: ATLASENT_API_KEY, ATLASENT_BASE_URL, ATLASENT_ORG_ID env vars.
"""

import os
import sys

from atlasent import AtlaSentClient
from atlasent.exceptions import AtlaSentError
from atlasent.scim import (
    scim_create_group,
    scim_create_user,
    scim_delete_user,
    scim_patch_group,
    scim_patch_user,
)

API_KEY = os.environ.get("ATLASENT_API_KEY")
BASE_URL = os.environ.get("ATLASENT_BASE_URL")
ORG_ID = os.environ.get("ATLASENT_ORG_ID")

if not API_KEY or not BASE_URL or not ORG_ID:
    print(
        "ATLASENT_API_KEY, ATLASENT_BASE_URL, and ATLASENT_ORG_ID are all required.",
        file=sys.stderr,
    )
    sys.exit(1)


def main() -> None:
    client = AtlaSentClient(api_key=API_KEY, base_url=BASE_URL)

    # ── Step 1: provision a new user ─────────────────────────────────────────
    user_payload = {
        "userName": "dana.example@acme.internal",
        "name": {"givenName": "Dana", "familyName": "Example"},
        "emails": [{"value": "dana.example@acme.internal", "primary": True}],
        "active": True,
    }

    print("Provisioning user:", user_payload["userName"])
    created_user = scim_create_user(client, ORG_ID, user_payload)
    user_id = created_user["id"]
    print("  Provisioned user id:", user_id)

    # ── Step 2: deactivate the user via PATCH ─────────────────────────────────
    # RFC 7644 §3.5.2 PatchOp — replace the active attribute.
    print("Deactivating user via PATCH...")
    patched_user = scim_patch_user(
        client,
        ORG_ID,
        user_id,
        [{"op": "replace", "path": "active", "value": False}],
    )
    print("  active after patch:", patched_user.get("active"))

    # ── Step 3: create a group ────────────────────────────────────────────────
    group_payload = {"displayName": "Deprovisioned Users"}

    print("Creating group:", group_payload["displayName"])
    created_group = scim_create_group(client, ORG_ID, group_payload)
    group_id = created_group["id"]
    print("  Created group id:", group_id)

    # ── Step 4: add the user to the group via PATCH ───────────────────────────
    print("Adding user to group...")
    patched_group = scim_patch_group(
        client,
        ORG_ID,
        group_id,
        [
            {
                "op": "add",
                "path": "members",
                "value": [{"value": user_id, "display": user_payload["userName"]}],
            }
        ],
    )
    members = patched_group.get("members") or []
    print("  Group member count after patch:", len(members))

    # ── Step 5: deprovision the user ──────────────────────────────────────────
    print("Deprovisioning user (DELETE)...")
    scim_delete_user(client, ORG_ID, user_id)
    print("  User deprovisioned.")


if __name__ == "__main__":
    try:
        main()
    except AtlaSentError as exc:
        print(f"AtlaSent error (status={exc.status_code}): {exc}", file=sys.stderr)
        sys.exit(1)
