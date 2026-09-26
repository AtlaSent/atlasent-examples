/**
 * auth-token-refresh — demonstrates multi-IdP token refresh via the
 * AtlaSent TypeScript SDK client.auth sub-client.
 *
 * Typical use case: a background service holding a refresh token that
 * needs to rotate credentials before expiry.
 */

import { AtlaSentClient } from "@atlasent/sdk";

const client = new AtlaSentClient({
  apiKey: process.env.ATLASENT_API_KEY!,
  baseUrl: process.env.ATLASENT_API_URL ?? 'https://api.atlasent.io/functions/v1',
});

async function main() {
  // 1. List available IdP connections for this org
  const connections = await client.auth.listIdpConnections();
  console.log("IdP connections:");
  for (const conn of connections) {
    const marker = conn.isDefault ? " (default)" : "";
    console.log(`  ${conn.id}  ${conn.name}  [${conn.provider}]${marker}`);
  }

  // 2. Refresh using the default IdP
  const currentRefreshToken = process.env.ATLASENT_REFRESH_TOKEN!;
  const tokens = await client.auth.refresh(currentRefreshToken);
  console.log(`\nRefreshed via default IdP:`);
  console.log(`  access_token: ${tokens.accessToken.slice(0, 12)}...`);
  console.log(`  expires_in:   ${tokens.expiresIn}s`);

  // 3. If the org has a named Okta connection, refresh against it specifically
  const okta = connections.find(c => c.provider === "okta");
  if (okta) {
    const idpTokens = await client.auth.refreshWithIdp(okta.id, currentRefreshToken);
    console.log(`\nRefreshed via ${okta.name}:`);
    console.log(`  access_token: ${idpTokens.accessToken.slice(0, 12)}...`);
    console.log(`  idp_id:       ${idpTokens.idpId}`);
  }
}

main().catch(console.error);
