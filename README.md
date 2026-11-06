# Calibration System

![CI](https://github.com/ernestog-cmd/calibration-system/actions/workflows/ci.yml/badge.svg)

REST API to manage measurement equipment in a regulated manufacturing environment (ISO / FDA style). It tracks which instruments exist, when they were calibrated, when they expire, and in which production lots each one was used, so a failed calibration can be traced back to the affected lots.

Built with FastAPI, SQLAlchemy 2 and pytest.

## Features

- **Equipment registry** with search and filters (type, location, status, calibration state).
- **Calibration records** with an automatically computed due date and a computed state: valid, due soon (30 days), expired, or not required (fixtures and tooling).
- **Automatic out-of-service** when a calibration fails or is out of tolerance. Bringing equipment back is a deliberate admin action.
- **Lot traceability:** usage records link equipment to lots, part numbers and operations. Search by equipment ("where was it used?") or by lot ("which equipment took part?").
- **Usage blocking:** equipment that is expired, out of service or retired cannot be used. The calibration state at the moment of use is stored with each record.
- **Audit log** written in the same transaction as each change, with old and new values. Entries cannot be edited or deleted through the application. Password hashes are never logged.
- **Calibration certificates** (PDF upload and download, validated by content, stored under a server-generated name, SHA-256 recorded in the audit log).
- **Daily alert digest** (scheduled job) of expired and soon-to-expire equipment, sent by email or written to the log when SMTP is not configured.
- **Reports and CSV export** (equipment, usage, calibrations) with protection against spreadsheet formula injection.
- **Role-based access:** admin, technician, auditor.
- **JWT authentication** with bcrypt password hashing. Deactivated users are blocked immediately.

## Roles

| Action | Admin | Technician | Auditor |
|---|---|---|---|
| Manage users | yes | no | no |
| Create and edit equipment | yes | no | no |
| Register calibrations, certificates and usage | yes | yes | no |
| Read equipment, calibrations, usage, reports | yes | yes | yes |
| Read the audit log | yes | no | yes |

## Design decisions

- Calibration state is **computed** from the last calibration that passed, never stored, so it cannot go stale.
- Records are append-only: calibrations and audit entries are never edited. A correction is a new record.
- The audit entry and the change it describes are committed together, so one cannot exist without the other.
- Users and equipment are never deleted, only deactivated or retired, to keep history traceable.
- The lot id is plain text, so the project does not depend on any other system's database.

## Getting started

Requires Python 3.12 or newer.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt

python -m scripts.create_user    # creates the first admin (choose the role "admin")
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000/docs for the interactive API documentation. Use the **Authorize** button to log in.

## Configuration

Everything is optional. Without any variable the app runs with SQLite and logs the alert digest instead of emailing it.

| Variable | Purpose | Default |
|---|---|---|
| `DATABASE_URL` | Database connection string | `sqlite:///./calibration.db` |
| `SECRET_KEY` | JWT signing key (**set a long random value in production**) | development value |
| `UPLOAD_DIR` | Where certificates are stored | `uploads` |
| `ENABLE_SCHEDULER` | Run the daily alert job | `true` |
| `ALERT_HOUR` / `ALERT_TIMEZONE` | When the job runs | `7` / `America/Tijuana` |
| `ALERT_RECIPIENTS` | Comma-separated emails for the digest | empty |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_STARTTLS` | Email server | empty |

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

The suite (135 tests) covers authentication, permissions, equipment, calibration rules, usage blocking and search, the audit log, certificates, alerts and reports. It runs on every push with GitHub Actions.

## Project structure

```
app/
  main.py            application and scheduler startup
  models.py          SQLAlchemy models
  schemas.py         request and response schemas
  security.py        password hashing and JWT
  dependencies.py    current user and role checks
  routers/           auth, users, equipment, calibrations, certificates,
                     usage, alerts, reports, audit
  services/          calibration state, audit log, alerts, scheduler, storage
scripts/             create_user.py
tests/               pytest suite
```

## Roadmap

- Frontend.
- Database migrations (Alembic), Docker and a public deployment.
- Email per responsible user.
- External storage for certificates.