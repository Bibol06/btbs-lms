# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

BTBS LMS: Django 5.2 backend (`backend/`), React 19 + TypeScript + Vite frontend (`frontend/`), PostgreSQL. The user communicates in Russian; project docs (`*_RU.md`, most root `.md` files) are in Russian. Host OS is Windows; a Docker stack runs the production-like setup.

## Commands

Backend (run from `backend/`, Windows venv at `.venv/Scripts/`):

```sh
.venv/Scripts/python.exe manage.py runserver 127.0.0.1:8000
.venv/Scripts/python.exe manage.py test --settings=config.test_settings            # full suite, needs local PostgreSQL
.venv/Scripts/python.exe manage.py test codejudge.test_queue.QueuedCodeCheckTests.test_inline_mode_answers_with_verdict --settings=config.test_settings
.venv/Scripts/ruff.exe check .
.venv/Scripts/python.exe manage.py makemigrations --check --dry-run
.venv/Scripts/python.exe manage.py setup_code_runner                                # downloads the WASI Python runtime; sandbox tests are skipped without it
```

Dependencies: edit the ranges in `requirements*.txt`, then run `.venv/Scripts/python.exe lock_requirements.py` (add `-P <pkg>` to upgrade a package) to regenerate the hashed `requirements.lock` (Docker image) and `requirements-dev.lock` (CI, local venv: `pip install --require-hashes -r requirements-dev.lock`). CI fails if a lock is stale or if pip-audit finds a vulnerability.

Always use `config.test_settings` for tests: it forces local media storage, disables Redis, S3 backup upload and Sentry, and leaves Celery without a broker, so tasks run inline.

Frontend (from `frontend/`): `npm run dev` (Vite on 127.0.0.1:5173 proxies `/api` to :8000), `npm run lint`, `npm run build` (runs `tsc -b`). There is no frontend test runner.

Windows launchers in the repo root: `Start-LMS.ps1` (dev servers + worker loops), `Start-LMS-Containers.ps1`, `Start-LMS-Share.ps1` (Waitress + Cloudflare tunnel).

Docker stack: `docker compose -f deployment/compose.yaml up -d` (web on Gunicorn, nginx on 127.0.0.1:8080, redis, Celery `worker-judge`/`worker`/`beat`). PostgreSQL is NOT in the stack: containers reach the Windows service through `host.docker.internal`. Rebuild with `docker compose -f deployment/compose.yaml build web`; workers reuse the `btbs-local-web` image.

Load test: `deployment/RUN_LOAD_ON_SERVER_RU.md` (`deployment/compose.load.yaml`, env `BENCH_SERVER`, `BENCH_ACTIVITIES`, …). The probe (`backend/load_probe_local.py`) creates and drops a disposable `test_btbs_load_*` database. Results are logged in `PERFORMANCE_INVESTIGATION_RU.md`.

CI (`.github/workflows/ci.yml`): ruff, `check`, `check --deploy`, migrations check, `setup_code_runner`, tests on PostgreSQL 16, pip-audit (non-blocking), npm lint/build/audit. `gh` lives at `"/c/Program Files/GitHub CLI/gh.exe"` (not on PATH in Bash).

## Architecture

### Domain model (see `ARCHITECTURE_NEXT.md`, `PLATFORM_V2.md`)

`Course` (content) → `Module` → `Lesson` → `Step` (text/video/material/quiz/assignment/code). Delivery is a `CourseRun`, either `self_paced` or a `cohort` with a schedule. A student's participation is an `Enrollment` bound to a run. Progress, submissions, quiz attempts, deadlines (`ActivitySchedule`, `AssignmentExtension`, module releases) and checkpoints are per enrollment/run. Most endpoints take `?run_id=`.

Apps: `accounts` (users, roles, login guard, recovery, backups), `courses` (courses, runs, enrollment, access, pacing), `learning` (modules/lessons/steps, progress, media), `assessment` (assignments, quizzes, deadlines; mounted at `/api/study/`), `communication` (notifications, discussions), `codejudge` (Python exercises; mounted at `/api/code/`), `analytics`, `workspace`.

### API conventions

- Views are plain Django function views wrapped in `common.api` (`backend/common.py`). It turns `ApiError(message, status)` into `{"error": ...}` JSON. Use the input helpers in `common.py` (`body`, `text`, `raw_text`, `integer`, `boolean`, `authenticated`). DRF is installed but not used by views.
- Error messages are Russian source strings. Both i18n catalogs translate them (see below).
- Access checks live in `courses/access.py` (`can_manage_course`, `can_manage_run`, `resolve_run`, `require_run`, `require_learning_enrollment`, `managed_run_ids`) and in `learning/services.py` (`require_lesson_visible`, `require_activity_visible`, prerequisites, `course_progress`).
- Performance: query counts are guarded by `learning/test_performance.py`. When you touch dashboard/structure/deadline code, keep batching: prefetch with `to_attr`, the `*_many` helpers (`course_progress_many`, `module_deadline_states_many`) and per-request memo attributes on the run object (`_prerequisite_cache`, …). Do not add per-course or per-lesson queries.

### Localization

- System captions: the Russian string is the key in `frontend/src/i18n/messages.json` and `backend/locales/messages.json`, mapping to `[kk, en]`. The two files must be identical (enforced by `accounts/test_localization.py`). When you add a user-facing string, add it to both, keeping `{0}` slots.
- Authored course content is never machine-translated. `content_localization.ContentTranslationMiddleware` attaches author-provided translations to `/api/` JSON responses (it adds a `_course_policy` key when a run is involved).

### Frontend

A single app without a router. `App.tsx` plus `workspaces.ts` derive the page from `location.hash` (role workspaces: student/teacher/admin). API calls go through `apiRequest` in `src/api.ts`, which handles CSRF and throws on non-2xx. UI strings go through `t()` / `localizedLabels` from `src/i18n/language`.

### Background work (`deployment/BACKGROUND_TASKS_RU.md`)

- Celery app in `config/celery.py`; schedule in `CELERY_BEAT_SCHEDULE` (`config/settings.py`). If `LMS_CELERY_BROKER_URL` is empty, `CELERY_TASK_ALWAYS_EAGER` is on and tasks run inline. This is the mode for Windows dev and tests.
- Periodic tasks (`*/tasks.py`) wrap the same functions the legacy management-command loops call (`notification_worker`, `maintenance_worker`, `analytics_snapshots`, `cleanup_media_uploads`). Keep both entry points working. `background.exclusive` prevents overlapping runs.
- Code checks: `codejudge/views.execute` queues `judge_submission` / `practice_run` (queue `judge`) and returns 202. The client polls `/api/code/submissions/<id>/` or `/api/code/runs/<token>/`. In eager mode it returns 200 with the verdict. Student code runs only inside a WASI interpreter under wasmtime (`codejudge/worker.py`) with fuel/memory/output limits; never execute user code on the host.
- Backups (`backup_lms`, encrypted, optional S3 copy) run from Windows Task Scheduler (`Install-LMS-BackupTask.ps1`), not Celery.

### Deployment specifics

- Container serves `config.proxy_wsgi:application` via `backend/gunicorn.conf.py`. Gunicorn does not rewrite `REMOTE_ADDR`, so `proxy_wsgi` takes the right-most `X-Forwarded-For` entry. Login throttling and recovery limits depend on it.
- Settings modules: `config.settings` (base, env-driven via `backend/.env`), `config.container_settings` (Docker), `config.test_settings`, `config.share_settings` (temporary public link).
- Media: `MEDIA_STORAGE_MODE` is `local` or `s3` (`media_storage.HybridMediaStorage`, CloudFront signed URLs in `cdn.py`). Nginx returns 404 for `/admin/` and `/media/`.
- Redis runs with `volatile-lru` because it is both cache (db 1) and Celery broker (db 2). Cache entries must always have a timeout.
- `.local/` holds runtime state (logs, backups, backup keys, WASI runtime, load reports, demo credentials) and is git-ignored.
