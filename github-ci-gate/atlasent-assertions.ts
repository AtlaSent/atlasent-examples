/**
 * atlasent-assertions.ts
 *
 * TypeScript helper that wraps @atlasent/sdk for submitting CI assertions
 * from a Node.js build/deploy script.
 *
 * Usage:
 *   import { assertCIPassed } from './atlasent-assertions.js';
 *
 *   await assertCIPassed({
 *     sha:   process.env.GITHUB_SHA!,
 *     repo:  process.env.GITHUB_REPOSITORY!,
 *     actor: process.env.GITHUB_ACTOR!,
 *     runId: process.env.GITHUB_RUN_ID!,
 *   });
 *
 * Prerequisites:
 *   npm install @atlasent/sdk
 *   export ATLASENT_API_KEY=ask_live_...
 */

import { AtlaSentClient, type AssertionSubmitResult } from "@atlasent/sdk";

const client = new AtlaSentClient({
  apiKey: process.env.ATLASENT_API_KEY!,
  baseUrl: process.env.ATLASENT_API_URL ?? 'https://api.atlasent.io/functions/v1',
});

/**
 * Submit a `github.ci_passed` assertion for the given commit SHA.
 *
 * Records that CI tests passed for this exact SHA so that your AtlaSent
 * policy for `production.deploy` can require `context.activeAssertions`
 * to contain `'github.ci_passed'` before issuing a permit.
 *
 * The assertion is valid for 24 hours from submission time. Submitting
 * the same assertion within the TTL returns the existing record with
 * `reused: true` — safe to call on every push without creating duplicates.
 *
 * Requires API key scope: `assertions:write`.
 */
export async function assertCIPassed(opts: {
  /** The git commit SHA, e.g. `process.env.GITHUB_SHA`. */
  sha: string;
  /** The repository slug, e.g. `process.env.GITHUB_REPOSITORY` (`owner/repo`). */
  repo: string;
  /** The actor that triggered the CI run, e.g. `process.env.GITHUB_ACTOR`. */
  actor: string;
  /** The GitHub Actions run ID, e.g. `process.env.GITHUB_RUN_ID`. */
  runId: string;
}): Promise<AssertionSubmitResult> {
  return client.submitAssertion({
    assertion_type: "github.ci_passed",
    source_system: "github",
    subject_ref: `${opts.repo}@${opts.sha}`,
    actor_id: opts.actor,
    action_type: "production.deploy",
    payload: {
      run_id: opts.runId,
      sha: opts.sha,
      repo: opts.repo,
    },
    trust_level: "attested",
    valid_until: new Date(Date.now() + 24 * 3_600_000).toISOString(),
  });
}
