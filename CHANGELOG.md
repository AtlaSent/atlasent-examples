# Changelog

All notable changes to this repository are documented here. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). This
repository contains examples rather than a versioned package, so entries are
grouped by date.

## [Unreleased]

### Added
- `CONTRIBUTING.md` explains how to run examples, how to contribute and where
  to report security issues.
- `CHANGELOG.md` (this file).

### Changed
- References to the former `AtlaSent-Systems-Inc` GitHub organization now use
  `Atlasent`. This includes `uses: Atlasent/atlasent-action@...` in the
  workflow examples.
- README is rewritten for external developers: the internal-only package
  pointer is removed and the primary scenario is described more plainly.
- TypeScript is upgraded to 7.x in 24 example directories. `accounting-close`
  now sets `"types": ["node"]` (TS 7 no longer includes `@types/*` by default)
  and `salesforce-deploy-gate` uses `moduleResolution: "bundler"` (TS 7 removed
  `"node"`). `compliance-evidence` and `webhook-receiver` run with `tsx`
  instead of `ts-node`, which does not work with TS 7. `@types/node` stays on
  20.x to match the Node version CI uses.
- Dependabot no longer opens major-version PRs for `typescript` or
  `@types/node`. These upgrades are done by hand.

## 2026-09-26 — First public release

### Added
- First public publish of the AtlaSent examples: GitHub Actions, GitLab CI,
  Node, Python, Go, LangChain, LlamaIndex and MCP integrations that gate
  protected actions with `evaluate` and `verify-permit`.
- Dependabot npm updates for every example directory.
