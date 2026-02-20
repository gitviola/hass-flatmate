# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Home Assistant flat-sharing toolkit with three components:
- **`addon/hass_flatmate_service/`** — Canonical backend source (FastAPI + SQLite). All backend edits go here.
- **`apps/hass_flatmate_service/`** — HA App packaging (Dockerfile, config). `service_src/` is a mirror of `addon/` for Docker builds.
- **`custom_components/hass_flatmate/`** — HA custom integration (HACS): entities, services, coordinator, frontend cards.

## Commands

```bash
# Run backend tests (primary development loop)
cd addon/hass_flatmate_service && pytest

# Or via Makefile from repo root
make test

# Run a single test
cd addon/hass_flatmate_service && pytest tests/test_cleaning_api.py::test_function_name

# Install test dependencies (first time / after pyproject.toml changes)
cd addon/hass_flatmate_service && pip install -e '.[test]'

# Sync backend source to app build mirror (required after backend changes, CI enforces this)
./scripts/sync_app_service_src.sh
# or: make sync-app-source

# Validate frontend card JavaScript syntax
node --check custom_components/hass_flatmate/frontend/hass-flatmate-shopping-card.js
node --check custom_components/hass_flatmate/frontend/hass-flatmate-cleaning-card.js
node --check custom_components/hass_flatmate/frontend/hass-flatmate-distribution-card.js

# Compile-check the integration Python
python -m compileall custom_components/hass_flatmate
```

## Architecture

### Data flow

Integration (HA) syncs persons to backend via `POST /members/sync` → Backend owns all domain state (shopping, cleaning, activity) in SQLite → Integration polls backend every 60s via coordinator → Backend returns notifications due for the current minute → Integration dispatches via HA `notify.*` services → Frontend cards call integration services → Integration marshals to backend API.

### Backend (FastAPI)

- `app/main.py` — All API routes + token auth middleware (`X-Flatmate-Token` header)
- `app/models.py` — SQLAlchemy ORM models
- `app/schemas.py` — Pydantic request/response schemas
- `app/services/cleaning.py` — Rotation logic, swap/override management, notification scheduling
- `app/services/shopping.py` — Shopping list CRUD, favorites, stats, distribution
- `app/services/members.py` — Member sync from HA persons
- `app/settings.py` — Env-based config (`HASS_FLATMATE_API_TOKEN`, `HASS_FLATMATE_DB_PATH`, etc.)

### Integration (custom component)

- `__init__.py` — Platform setup, service registration, event bus listeners
- `api.py` — HTTP client to backend
- `coordinator.py` — Polling data coordinator
- `sensor.py` — Sensor entities (shopping data, cleaning schedule, distribution)
- `frontend/*.js` — Lit-based custom Lovelace cards (shadow DOM)

### Testing

- pytest with FastAPI TestClient, temporary SQLite DB per test (`tmp_path` fixture)
- Auth via `X-Flatmate-Token: test-token` header fixture
- No mocking frameworks — tests exercise the full API stack

## Releasing

**After any functional change (bugfix, feature, etc.), always do a release.** The tag triggers the CI/CD pipeline that builds and publishes the HA add-on and HACS integration. No tag = no release = users don't get the fix.

Steps:
1. Update version in both `apps/hass_flatmate_service/config.yaml` and `custom_components/hass_flatmate/manifest.json`.
2. Commit with message `release X.Y.Z`.
3. **Always create and push a git tag**: `git tag vX.Y.Z && git push origin vX.Y.Z`. Never forget the tag — the release is not complete without it.
4. Push both the commits and the tag: `git push origin main && git push origin vX.Y.Z`.

Use patch bumps (0.1.X → 0.1.X+1) for bugfixes, minor bumps for features.

## Git Workflow

- **Override global rule**: In this repo, you may `git add` and `git commit` on your own without asking first.
- Never co-author commits with Claude (no `Co-Authored-By` trailer).
- Never `git amend` — commits may already be pushed.

## Key Development Rules

- **Always edit `addon/hass_flatmate_service/`**, never `apps/.../service_src/` directly. Run `sync_app_service_src.sh` after backend changes.
- CI enforces the sync: `git diff --exit-code -- apps/hass_flatmate_service/service_src` must be clean.
- Version must match in both `apps/hass_flatmate_service/config.yaml` and `custom_components/hass_flatmate/manifest.json` for releases.
- Python 3.12+ required. No linter/formatter configured — follow existing code style.
- Frontend cards are vanilla JS (Lit patterns, shadow DOM). No build step; validate with `node --check`.
- Entity IDs use domain prefix `hass_flatmate_` (e.g., `sensor.hass_flatmate_shopping_data`).
