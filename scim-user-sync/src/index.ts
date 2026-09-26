// Demonstrates: provisioning a user, updating their active status via PATCH,
// adding them to a group, then deprovisioning via DELETE.
//
// Flow: scimCreateUser -> scimPatchUser (active: false) -> scimCreateGroup
//       -> scimPatchGroup (add member) -> scimDeleteUser
//
// Requires: ATLASENT_API_KEY, ATLASENT_BASE_URL, ATLASENT_ORG_ID env vars.

import {
  AtlaSentClient,
  type ScimUserInput,
  type ScimGroupInput,
  type ScimPatchOp,
} from "@atlasent/sdk";

const SCIM_USER_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:User";
const SCIM_GROUP_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:Group";
const SCIM_PATCH_OP_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:PatchOp";

const apiKey = process.env["ATLASENT_API_KEY"];
const baseUrl = process.env["ATLASENT_BASE_URL"];
const orgId = process.env["ATLASENT_ORG_ID"];

if (!apiKey || !baseUrl || !orgId) {
  console.error(
    "ATLASENT_API_KEY, ATLASENT_BASE_URL, and ATLASENT_ORG_ID are all required.",
  );
  process.exit(1);
}

const client = new AtlaSentClient({ apiKey, baseUrl });

async function main() {
  // ── Step 1: provision a new user ─────────────────────────────────────────
  const userInput: ScimUserInput = {
    schemas: [SCIM_USER_SCHEMA],
    userName: "dana.example@acme.internal",
    name: { givenName: "Dana", familyName: "Example" },
    emails: [{ value: "dana.example@acme.internal", primary: true }],
    active: true,
  };

  console.log("Provisioning user:", userInput.userName);
  const createdUser = await client.scimCreateUser(orgId, userInput);
  const userId = createdUser.id!;
  console.log("  Provisioned user id:", userId);

  // ── Step 2: deactivate the user via PATCH ─────────────────────────────────
  // RFC 7644 §3.5.2 PatchOp — replace the active attribute.
  const deactivateOp: ScimPatchOp = {
    schemas: [SCIM_PATCH_OP_SCHEMA],
    Operations: [{ op: "replace", path: "active", value: false }],
  };

  console.log("Deactivating user via PATCH...");
  const patchedUser = await client.scimPatchUser(orgId, userId, deactivateOp);
  console.log("  active after patch:", patchedUser.active);

  // ── Step 3: create a group ────────────────────────────────────────────────
  const groupInput: ScimGroupInput = {
    schemas: [SCIM_GROUP_SCHEMA],
    displayName: "Deprovisioned Users",
  };

  console.log("Creating group:", groupInput.displayName);
  const createdGroup = await client.scimCreateGroup(orgId, groupInput);
  const groupId = createdGroup.id!;
  console.log("  Created group id:", groupId);

  // ── Step 4: add the user to the group via PATCH ───────────────────────────
  const addMemberOp: ScimPatchOp = {
    schemas: [SCIM_PATCH_OP_SCHEMA],
    Operations: [
      {
        op: "add",
        path: "members",
        value: [{ value: userId, display: userInput.userName }],
      },
    ],
  };

  console.log("Adding user to group...");
  const patchedGroup = await client.scimPatchGroup(orgId, groupId, addMemberOp);
  console.log(
    "  Group member count after patch:",
    patchedGroup.members?.length ?? 0,
  );

  // ── Step 5: deprovision the user ──────────────────────────────────────────
  console.log("Deprovisioning user (DELETE)...");
  await client.scimDeleteUser(orgId, userId);
  console.log("  User deprovisioned.");
}

main().catch((err) => {
  console.error("Error:", err instanceof Error ? err.message : String(err));
  process.exit(1);
});
