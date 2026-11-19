# QA report: full site sweep (branch `qa/site-sweep`)

**Environment.** Isolated database `lms_qa`, local media, no S3/CloudFront/mail/Sentry (`backend/config/qa_settings.py`). The data comes from `manage.py seed_qa` plus the existing demo seeds. Frontend 5174 talks to backend 8100. Started with `tools/qa/start_qa.ps1`.

**How the sweep was run.** Playwright 1.64.1 on the installed Microsoft Edge (`frontend/e2e/`).
- **Coverage:**
  - 87 page × role combinations: guest, student, student without courses, teacher, course editor, group teacher, admin with full, learning and system scope;
  - ru at 1440/1024/768/390;
  - kk and en at 1440, run serially so the profile language does not race between tests.
- **Checks:**
  - console errors, failed API calls;
  - horizontal scroll, text off-screen or outside its card, clipping without ellipsis;
  - raw `undefined/null/NaN`;
  - untranslated UI strings (against `messages.json`);
  - duplicate labels, data smells;
  - broken images;
  - video playback;
  - axe-core serious/critical.
- **Screenshots** (ru 1440/390): `.local/qa/screens/<role>/<page>-<width>.png`. Not committed: there are about 175 large images. The before/after pairs for fixed items go to `docs/qa/screens/`.

**Raw results:** `.local/qa/sweep/results-layout2.jsonl` (layout), `results-i18n.jsonl` (kk/en).

Severity: 🔴 critical · 🟠 medium · 🟡 minor · ⚪ data (content problem, not code).

## Summary

| Severity | Found | Fixed | Deferred | Data |
|---|---:|---:|---:|---:|
| 🔴 | 1 | 1 (mitigated) | 0 | — |
| 🟠 | 7 | 6 | 1 (QA-015 unconfirmed) | — |
| 🟡 | 16 | 9 | 7 | — |
| ⚪ | 5 | 3 (UI help added) | — | 5 |

## Status per finding

| ID | Status | Commit / reason |
|---|---|---|
| QA-001 | ✅ mitigated | `0bc9047`: e2e uses 1 worker by default; memory guidance in `CLAUDE.md`. The machine itself still has 12 GB shared by many tools. |
| QA-010, QA-011 | ✅ | `6a4ee71`: scroll regions are focusable and labelled, edge shadows show hidden columns; tab rows scroll on phones. |
| QA-012, QA-013 | ✅ | `06732f8`: title-carrying buttons wrap; other buttons cannot widen their container; outline items have tooltips. |
| QA-014 | ✅ | `06732f8`: "Модуль N · Урок M · Шаг K" from ordinal numbers (API + regression test `workspace/test_preview_numbering.py`). |
| QA-015 | ⏸ | Not confirmed. Sweep timings include harness waits; needs a direct API timing check. |
| QA-016 | ✅ | `39b5ac8`: one primary button, natural-width form buttons, plan editor replaced with a link to its tab. |
| QA-020 | ✅ | `6ebb9d0`: `--text-subtle` and legacy greys now pass AA (4.5:1+) on all surfaces. |
| QA-021, QA-022 | ✅ | `06732f8`: loading state in the preview; "Пройдено в предпросмотре шагов: N". "Оригинал сообщения" kept (it labels the untranslated original of a discussion message). |
| QA-024–QA-028, QA-033 | ✅ | `722aa49`: player tooltips, no stretched empty card, dates without seconds, cover initials ignore "QA:"-style prefixes, compact language badge, no duplicate fullscreen attribute. |
| QA-023 | ⏸ | Guest 401 on `/api/auth/me/` is the app's session probe. Changing it is an API contract change; the e2e suite treats it as expected. |
| QA-029, QA-030, QA-031, QA-035 | ⏸ | Legacy styling and course cards belong to redesign phases 3–4 (`frontend/REDESIGN_PLAN.md`); no functional error. |
| QA-032 | ⏸ | GET views finalizing quiz attempts are a safety net while Windows dev runs without Celery beat; remove together with the beat-only setup. |
| QA-034 | ⏸ | A 403 for a direct link to a locked step is the correct response; the player shows the lock message. |
| QA-040–QA-042 | ⚪ + UI help | `8e9af8b`: readable default titles for uploads (`learning/naming.py` + test), pre-filled editable title in the uploader, editor warnings for digit-only, file-name-like and duplicate titles. Existing content is not renamed. |
| QA-043, QA-044 | ⚪ | Content issues (C++ course with Python content, empty descriptions); the readiness check already lists missing descriptions. |

## Guards added (step 3)
- `npm run e2e` (`frontend/e2e/smoke.spec.ts`): key pages for guest, student, teacher and admin at 1440 and 390 px through the UI audit, which fails on console/HTTP errors, overflow, clipped text, raw values, duplicate labels, broken media and axe serious/critical. Scenarios: "Понятно!" completes a step, a Python practice run shows output, preview numbering is unique.
- `npm run check:i18n`: catalogs complete and identical, no raw Russian JSX text. Runs in CI.
- CI job `e2e`: PostgreSQL service, `seed_qa`, Django with `qa_settings`, Vite, Playwright chromium, `npm run e2e`.
- `CLAUDE.md` "UI quality rules" and `.github/pull_request_template.md`.

**What is in good shape:**
- **Translations.** kk has no untranslated UI strings. In en, every Cyrillic string found is authored content: course, lesson and step titles and people's names.
- **Errors and access.** No uncaught exceptions on any page. No permission gaps were found by the static review (all `@api` views go through `require_*`, `authenticated` or role helpers).
- **Video.** Local video and YouTube load and play in the player. The video stuck at 0:00 from the owner's screenshot was served from S3/CloudFront, which QA does not use; see "Manual checks".

## Findings

### 🔴 Critical

| ID | Where | What happens | Cause / note |
|---|---|---|---|
| QA-001 | whole site (dev machine) | During the first sweep PostgreSQL hit "out of memory". It crash-restarted and then hung in recovery: every API call returned 500 and it needed a manual admin `Stop-Process postgres` + `Start-Service`. | 11.7 GB RAM shared by pgAdmin, Docker/WSL, VS Code, two backends, two Vite servers, workers and 3 parallel Edge browsers. Not an app-code bug: the e2e default is now 1–2 workers. The Docker stack has memory limits; the bare Windows dev setup has none. Recommendation in `CLAUDE.md` (step 3). |

### 🟠 Medium

| ID | Role · page · width | What happens | Suspected cause |
|---|---|---|---|
| QA-010 | admin · Users · 1024/768/390 | The users table is wider than the screen: email is cut, and role, status and the "Удалить" button are off-screen with no visible horizontal scroll. | `users-table` has no scroll wrapper or stacked mobile layout (`pages/admin/UsersPage.tsx`, `UsersPage.css`). |
| QA-011 | teacher / learning admin · Analytics · 390 | The learners and materials tables run off-screen ("Ответы и прогресс →", "Не зафиксировано" cut). axe: scrollable region not keyboard-focusable. | `analytics-table` without a responsive wrapper (`pages/analytics/Analytics.css`). |
| QA-012 | teacher · Student preview (course with long titles) · 1440/1024 | The whole page scrolls horizontally (1567 px). | Preview outline buttons do not wrap long step titles (`pages/workspace/CoursePreview.tsx`, `.preview-outline button`). |
| QA-013 | teacher · Course editor outline · all widths | Long step titles are cut mid-word without an ellipsis and spill outside the outline card ("1. Уроки_Python_с_нуля_#1 – Програм"). | `.lesson-sidebar .lesson-item` lacks `min-width:0` + wrap/ellipsis + `title` (`Brand.css`, `CourseWorkspace.css`). This is the owner's screenshot issue. |
| QA-014 | teacher · Student preview · all | Steps are labelled "‹module title› · ‹lesson title›". With titles like "1" this reads "1 · 1", and all steps of a lesson get the same label: the "шаг 1 · 1" from the owner's screenshot. | `CoursePreview.tsx` outline label uses names, not positions. Expected: "Модуль N · Урок M" plus step number. |
| QA-015 ⏸ | several pages, all roles | **Not confirmed.** Pages took 9–14 s to "settle" in the sweep and 12 tests exceeded 120 s for 4 widths. Part of this is the harness: it waits for a quiet API window while the app polls. Needs a direct API timing check before calling it a bug. | The 11 pages missing from the second layout pass (student analytics/catalog/messages/video-file step, admin overview/analytics/courses, learning-admin reviews, teacher bank/publication/draft editor) were covered by the first layout pass. Their re-run was stopped by Claude Code because the PC ran low on memory. |
| QA-016 | teacher · Course → Groups and team · all | Five filled primary buttons, four of them full width. "Учебный план" is duplicated inside "Управление группами" although it has its own tab. The page is one very long column of forms. | `pages/courses/GroupSettings.tsx`. Violates the design spec (one primary per view). |

### 🟡 Minor

| ID | Where | What happens | Suspected cause |
|---|---|---|---|
| QA-020 | all pages (footer), analytics period caption, deadline pills, discussion `small`, admin responsibility tags, readiness metrics, "черновик" badge, lesson progress, extension summary, lesson sidebar caption | Colour contrast below WCAG AA (axe serious, 151 hits). | `--text-subtle` (#7b8a9c) used for footer text (phase 2), plus legacy greys/teals in page CSS. |
| QA-021 | teacher · Student preview | For 1–2 s after opening, the page shows only the banner: no "Загрузка…" and no skeleton. | `CoursePreview.tsx` renders nothing while `data` is null. |
| QA-022 | teacher · Student preview; questions widget | Unclear labels: "Пробных отметок: N", "Оригинал сообщения". | `CoursePreview.tsx:34`, `components/PreparedText.tsx:16`. |
| QA-023 | guest · every page load | Console shows "401 Unauthorized" for `/api/auth/me/` on each visit. | The app checks the session via a 401. Could return 200 `{user: null}`. |
| QA-024 | student · Lesson player top bar · 768 | Course and lesson names are cut with an ellipsis but have no `title` tooltip. | `.player-crumbs` (`LessonPlayer.tsx`). |
| QA-025 | student · Player, short text step | The white card stretches to the full screen height, leaving a large empty area under one line of text. | `.player-article { min-height: calc(100% - 12px) }` (`LessonPlayer.css`). |
| QA-026 | My learning, teacher home, review cards | Dates show seconds ("23.11.2026, 22:58:32"). | `formatDate` in `pages/study/types.ts`. |
| QA-027 | teacher · My courses | Cover tiles show meaningless initials "QЧ", "QП" built from "QA: Черновик…". | Cover initials taken from the first letters including prefixes (`CourseCover`). |
| QA-028 | teacher · My courses | The "Язык курса: Русский" badge stretches across the whole card. | Badge rendered as a block (`CourseLanguageBadge` CSS). |
| QA-029 | course pages | Legacy styling still present: "ПРОГРАММА КУРСА" in caps, a squeezed "← Все курсы" button, "Открыть урок как ученик" / "Редактировать программу" each in its own bordered box (nested boxes), decorative circles on course covers. | Redesign phases 3–4 not done yet (`Brand.css` lesson-sidebar, `editor-switch`, `course-image`). |
| QA-030 | My learning | The "Обратная связь" card is a large empty box when there is no feedback. | No compact empty state. |
| QA-031 | My learning | Each course card has two buttons plus an "О курсе" link; the spec says the whole card is the link. | Phase 4. |
| QA-032 | backend · 7 GET views | Read endpoints write to the DB: `finalize_due_attempts` in agenda/course/report/management views, and `refresh_completion` in my-learning. | Safety net from before Celery beat. Now redundant with `communication.tasks.deadline_pass`; can be removed from GETs. |
| QA-033 | student · Player video (YouTube) | Console warning "Allow attribute will take precedence over 'allowfullscreen'". | `VideoLecture.tsx` sets both `allow="fullscreen"` and `allowFullScreen`. |
| QA-034 | student · locked step | A direct link to a locked step logs a 403 in the console. The UI handles it (message shown). | Expected status; the frontend could avoid requesting locked steps. |
| QA-035 | teacher · course editor | The step strip says "1 · Текст" while the outline says "1. <title>": two numbering styles for the same steps. | `Curriculum.tsx` `step-strip` vs outline. |

### ⚪ Data (content, not code)

These come from the seeded "QA: C++" course, which reproduces the owner's real course. The code should help the author (soft warnings in the editor) but must not rename content.

| ID | What | Suggested UI help |
|---|---|---|
| QA-040 | Module and lesson titled "1" | Editor warning: "Название состоит только из цифр". |
| QA-041 | Step titled with a raw file name "Уроки_Python_с_нуля_#1 – Программирование (360p, h264).mp4", also shown as "Ваш следующий шаг" | When uploading, suggest a readable title (no extension, `_`→space, drop 360p/h264); warn on existing ones. |
| QA-042 | Two steps both titled "шаг 1" | Warning: duplicate step titles in one lesson. |
| QA-043 | Course "C++" whose content is Python | Hard to detect automatically; a content-language/subject hint is optional. |
| QA-044 | Courses with an empty description | Readiness check already lists it; show it in the editor as well. |

## Manual checks (not covered by QA)
- **Video on S3/CloudFront** (the 0:00 spinner from the owner's screenshot). Check the content type, Range support and CORS of the signed URL in the browser network tab on the real setup.
- **S3 upload** (multipart), **CloudFront signing**, **Gmail delivery** of recovery mail, **backup to S3**.

## Static review notes
- **i18n.** JSX text outside `tr()`: only the language names "Русский" / "Қазақша", which is intentional.
- **Access.** All `@api` views have an explicit guard. Public by design: password recovery request/validate.
