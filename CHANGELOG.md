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

## 2026-09-26 — First public release

### Added
- First public publish of the AtlaSent examples: GitHub Actions, GitLab CI,
  Node, Python, Go, LangChain, LlamaIndex and MCP integrations that gate
  protected actions with `evaluate` and `verify-permit`.
- Dependabot npm updates for every example directory.
