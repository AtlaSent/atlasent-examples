> **Later-phase reference.** This document is not part of the Deploy Gate V1 pilot. Keep first pilots focused on GitHub Actions + `production.deploy` + `/v1-evaluate` + `/v1-verify-permit`.

# Policy Sync — GitOps Example

Store AtlaSent policies as code and apply them automatically via GitHub Actions.

## Structure

```
policy-sync-gitops/
  policies/
    bundle.json          # your policy definitions
  .github/workflows/
    policy-sync.yml      # CI workflow: diff on PR, apply on merge
```

## How It Works

1. Edit `policies/bundle.json` and open a PR.
2. The `policy-diff` job posts the bundle to AtlaSent in dry-run mode and comments the diff on the PR.
3. If the bundle is invalid, CI fails and the PR cannot merge.
4. When the PR merges to `main`, the `policy-apply` job posts with `dry_run: false` to apply the changes.

## Setup

1. Copy the `.github/workflows/policy-sync.yml` file into your own repository.
2. Add your AtlaSent API key as a repository secret named `ATLASENT_API_KEY`.
3. Copy `policies/bundle.json` as a starting point and customize it.
4. Push to your repository.

## Bundle Format

The complete policy entry schema and naming conventions are in AtlaSent's internal Policy Sync guide, which is not public yet.
