# Contributing to atlasent-examples

Thanks for your interest. This repository holds runnable examples of the
AtlaSent evaluate → permit → verify-permit flow. The examples are meant to
be copied and adapted, so fixes that make them clearer, more correct or
easier to run are welcome.

## Running an example

Each example directory is self-contained and has its own `README.md` with
the exact steps. In general:

- **Node / TypeScript examples:** `cd <example> && npm install`, then the
  scripts listed in that example's `package.json` (for example
  `npm run typecheck`, `npm test`, `npm start`).
- **Python examples:** most Python examples ship a `requirements.txt`. To
  list the ones that do:

  ```sh
  find . -name node_modules -prune -o -name requirements.txt -print
  ```

  For those, run `cd <example> && pip install -r requirements.txt`, then run
  the script named in the example's README. A few Python examples have no
  `requirements.txt` (currently `database-actions/migration-apply`,
  `database-actions/schema-drop`, `deployment-v2` and `scim-idp-sync`). They
  import only the Python standard library and the AtlaSent SDK, so install
  the SDK directly with `pip install atlasent`.
- **Go examples:** `cd <example> && go run main.go` (see the example's README).
- **GitHub Actions / GitLab CI examples:** copy the workflow into your own
  repository and set the secrets the example lists.

Examples that call a live AtlaSent API read `ATLASENT_API_KEY` and a base
URL (`ATLASENT_API_URL` or `ATLASENT_BASE_URL`, as documented per example)
from the environment. Never commit a real key. Many examples also have an
offline or dry-run mode that needs no credentials.

Before opening a pull request, run the repository-wide checks:

```sh
bash scripts/secret-leak-grep.sh
node scripts/check-action-names.mjs --self-test
node scripts/check-action-names.mjs
```

## Issues and pull requests

Issues and pull requests are welcome. Please:

- Keep each pull request focused on one example or one fix.
- Keep examples **fail-closed**: an example must never run a protected
  action when evaluation fails, errors, times out or returns anything
  other than a verified permit.
- Use dot-notation action types (for example `production.deploy`).
- Update the example's `README.md` when you change how it runs.

## Security

Please do **not** report security issues through public issues or pull
requests. Follow [SECURITY.md](SECURITY.md) instead.

## License

By contributing, you agree that your contributions are licensed under the
terms in [LICENSE](LICENSE).
