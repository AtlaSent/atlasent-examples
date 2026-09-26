#!/usr/bin/env python3
"""SCIM IdP sync — provision, update, and deprovision users via the AtlaSent
SCIM 2.0 sub-client. Mirrors what an Okta or Entra ID integration does under
the hood when using automatic provisioning."""

from __future__ import annotations

import os

from atlasent import AtlaSentClient
from atlasent.scim_client import ScimClient

ORG_ID = os.environ["ATLASENT_ORG_ID"]


def sync_users(scim: ScimClient, users: list[dict]) -> None:
    """Provision or update a batch of users, then print a summary."""
    print(f"syncing {len(users)} users to org {ORG_ID}")

    page = scim.users.list(org_id=ORG_ID, count=200)
    existing = {u["userName"]: u for u in page.get("Resources", [])}

    for user in users:
        username = user["userName"]
        if username in existing:
            user_id = existing[username]["id"]
            scim.users.update(org_id=ORG_ID, user_id=user_id, user=user)
            print(f"  updated  {username}")
        else:
            created = scim.users.create(org_id=ORG_ID, user=user)
            print(f"  created  {username}  →  {created['id']}")


def deprovision(scim: ScimClient, usernames: list[str]) -> None:
    page = scim.users.list(org_id=ORG_ID, count=200)
    by_name = {u["userName"]: u["id"] for u in page.get("Resources", [])}
    for username in usernames:
        if username in by_name:
            scim.users.delete(org_id=ORG_ID, user_id=by_name[username])
            print(f"  deprovisioned  {username}")
        else:
            print(f"  not found (skip)  {username}")


if __name__ == "__main__":
    client = AtlaSentClient(api_key=os.environ["ATLASENT_API_KEY"], base_url=os.environ.get("ATLASENT_API_URL", "https://api.atlasent.io/functions/v1"))
    scim = ScimClient(client)

    # Provision three users
    sync_users(scim, [
        {"userName": "alice@example.com", "active": True,
         "name": {"givenName": "Alice", "familyName": "Smith"},
         "emails": [{"value": "alice@example.com", "primary": True}]},
        {"userName": "bob@example.com", "active": True,
         "name": {"givenName": "Bob", "familyName": "Jones"},
         "emails": [{"value": "bob@example.com", "primary": True}]},
        {"userName": "carol@example.com", "active": True,
         "name": {"givenName": "Carol", "familyName": "Lee"},
         "emails": [{"value": "carol@example.com", "primary": True}]},
    ])

    print("\ndeprovisioning former employee:")
    deprovision(scim, ["carol@example.com"])
