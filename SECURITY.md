# Security Policy

## Reporting a vulnerability

If you discover a security vulnerability in this repository, **do not open a public GitHub issue**. Email [security@atlasent.io](mailto:security@atlasent.io) with:

- A description of the vulnerability and its potential impact
- Steps to reproduce or a proof-of-concept (if available)
- The version or commit SHA where you observed the issue
- Your contact information for follow-up

We acknowledge all reports within **2 business days**.

## Scope

| In scope | Out of scope |
|----------|--------------|
| `atlasent-examples` example code | The AtlaSent SaaS service itself |
| Example scripts that could enable credential leakage | Third-party services used in examples |
| Insecure patterns demonstrated in examples that could mislead users | Social engineering or phishing |

**Note:** These are reference examples, not production code. If an example demonstrates an insecure pattern that a user would copy into production, that is in scope.

## Supported versions

| Version | Supported |
|---------|-----------|
| Latest commit on `main` | Yes |
| Older versions | No |

## Disclosure policy

1. Reporter submits to security@atlasent.io
2. We acknowledge within 2 business days
3. We assess the impact (could the insecure example mislead production deployments?)
4. We fix the example and update any related documentation
5. Reporter is credited in the commit message unless they request anonymity

## Severity definitions

| Severity | Example | Target fix timeline |
|----------|---------|--------------------|
| High | Example hardcodes or logs credentials, example bypasses AtlaSent authorization | 7 days |
| Medium | Example missing error handling in ways that could produce silent auth failures | 30 days |
| Low | Confusing comments, misleading variable names | 90 days |

## Important notes for contributors

- **Never hardcode API keys** in example files. Always read from environment variables.
- **Never commit `.env` files.** The `.gitignore` in this repo excludes `.env` and `.env.local`.
- Examples should call `atlasent.evaluate()` (or `verify()`) and explicitly handle `deny` responses. Never write examples where the `deny` path is silently ignored.

## Security contact

- **Email**: security@atlasent.io
- **PGP**: Available on request
- **Response SLA**: 2 business days for acknowledgement
