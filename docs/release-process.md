# Release Process

SpotUI releases are immutable GitHub tags with a verified wheel, source
distribution, installer/uninstaller scripts, and a checksum manifest.

## Versioning

The canonical version is `__version__` in `src/spotui/__init__.py`.
`pyproject.toml` reads it through Hatchling's version source, so there is no
second Python version field and `uv.lock` records the project as dynamic. The
private frontend package also carries the version; a test fails when it
disagrees with the Python version.

Releases use `MAJOR.MINOR.PATCH` semantic versioning and tags of the form
`vMAJOR.MINOR.PATCH`.

## Prepare a release

1. Update the version in:
   - `src/spotui/__init__.py`
   - `frontend/package.json` and `frontend/package-lock.json`
     (`npm --prefix frontend install --package-lock-only`)
   - Run `uv lock` if dependency metadata changed.
2. Update user-facing documentation for behavior changes.
3. Run the full local gate:

```bash
uv sync --all-groups
(cd frontend && npm ci && npm test && npm run typecheck && npm run build)
uv run pytest
uv run ruff check .
uv lock --check
uv build
```

4. Confirm the wheel and sdist both contain
   `spotui/web/dist/index.html` and the generated asset files, and that the
   sdist contains `scripts/install.sh`, `scripts/uninstall.sh`, and the tests.
5. Install the built wheel into a clean environment without Node.js, apply
   migrations, and start the server. Verify the UI and
   `/api/v1/health`.
6. Exercise the dry-run and real legacy migration against a copy of a legacy
   queue.
7. Commit the version and documentation changes, then tag:

```bash
git tag -a v0.1.0 -m "SpotUI 0.1.0"
git push origin main
git push origin v0.1.0
```

The tag push starts `.github/workflows/release.yml`.

## Continuous integration

`.github/workflows/ci.yml` runs on pull requests and pushes to `main`:

- **Ubuntu 22.04:** frontend install/test/typecheck/build; backend tests; Ruff;
  `uv lock --check`; Alembic upgrade and drift check.
- **Arch Linux container:** backend tests and Ruff against the rolling Python
  and native environment.
- **Packaging:** builds the frontend and Python artifacts; verifies bundled
  assets in both wheel and sdist; installs the wheel in a clean uv environment;
  runs migrations, backup, and a real server health/UI smoke test; exercises the
  installer and uninstaller with the built wheel; uploads the distributions.

The release workflow calls the complete CI workflow before publishing. It will
not publish if any test, packaging, clean-install, or smoke check fails.

## Publish

`release.yml` performs these checks and steps:

1. Run the full CI workflow for the tagged commit.
2. Require `spotui-<tag version>-py3-none-any.whl` and
   `spotui-<tag version>.tar.gz` to exist.
3. Add both installer scripts and generate `SHA256SUMS` over every release
   asset.
4. Verify the checksum manifest.
5. Create the GitHub release with generated notes.

The repository must allow GitHub Actions to create releases (`Contents: write`
workflow permission, which the workflow requests explicitly).

## Verify a release

```bash
VERSION=0.1.0
BASE="https://github.com/runtime-terror404/spotui/releases/download/v${VERSION}"
curl -fLO "$BASE/SHA256SUMS"
curl -fLO "$BASE/spotui-${VERSION}-py3-none-any.whl"
sha256sum --check --ignore-missing SHA256SUMS
```

The installer repeats wheel verification automatically.

## Rollback boundaries

Publishing a fixed version is the normal rollback. Reinstall the previous
wheel or release version and keep the existing configuration.

Database schema changes are forward-only in normal operation. Every
`spotui db upgrade` made by the installer or CLI creates and verifies a backup
first, but Alembic downgrades are not guaranteed to preserve data created by
newer features. Do not promise a schema downgrade as rollback. To return to an
older application that cannot read the new schema, stop the server, restore the
verified backup made before the update, then install the older release. See
[installation.md](installation.md#backup-restore-and-rollback).

Never delete the previous release's wheel, the pre-update database backup, or
the `SHA256SUMS` manifest until the new release has been observed working.
