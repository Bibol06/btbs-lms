# Redesign plan (CSS-first, no behavior change)

Spec: `DESIGN_SPEC.md`. Each phase ships alone and is reviewed in the browser before the next.

## Findings
- `main.tsx` imports `index.css`. `App.tsx` imports `App.css`, `Workspace.css`, `Brand.css`, `WorkspaceHub.css`, in that order. `Brand.css` overrides most of the earlier rules.
- `Brand.css` holds three things: the `:root` tokens, element styles (h1 30px, h2 28px) and the app shell (`.layout`, `.topbar` 78px, `.sidebar` 252px, `.brand`, `.avatar`).
- Shell in `App.tsx` (~206–230):
  - `header.topbar` contains `.workspace-menu-toggle`, `.brand`, `.workspace-context`, `WorkspaceSearch` and `.header-actions`.
  - `.header-actions` holds `LanguageSwitcher`, `.notification-button`, `.account-button` and `.logout-button`.
  - `aside.sidebar` has captions, nav buttons and `.sidebar-logout`.
- Unclassed `button` = primary, `.secondary` = secondary (134 uses). There are 17 `!important`, in 7 files.

## Strategy
- **Tokens.** Create `src/styles/tokens.css`, imported first, with semantic tokens:
  - colors: `--bg --surface --surface-subtle --surface-brand --border --border-strong --text --text-muted --primary --primary-hover --primary-ink --navy --on-navy-muted --success/-bg --warning/-bg --danger/-bg --focus-ring`
  - type: `--fs-*` and `--lh-*`
  - spacing: `--sp-1..`
  - radii: `--r-ctl 6`, `--r-card 12`, `--r-sheet 16`, `--r-pill`
  - shadows `--sh-sm/md/lg`, plus motion and `--editor-*` tokens.
- **Legacy aliases.** Keep the old names (`--navy --teal --cyan --teal-soft --ink --muted --line --canvas --radius`) as aliases. Set `--muted` to #5b6b80 (fixes AA contrast) and `--radius` to 12px.
- **Base styles.** Add `src/styles/base.css` (reset, type, links, `:focus-visible` ring) and `src/styles/components.css` (buttons, inputs, cards, tabs, tables, badges, alerts, empty state, skeleton, menu, modal). Then add `shell.css`.
- **Precedence.** Use cascade layers: `@layer legacy, tokens, base, components, page;`. If layered imports are awkward in Vite, fall back to import order and verify visually.
- **Migration, per file in its phase:**
  - font sizes: 9–11px → 12, 13 → small, 14–15 → body, 16–17 → body-lg/h3, 18–24 → h2, 28+ → h1/display;
  - hex colors → role tokens (charts get `--chart-1..6`);
  - remove each `!important`;
  - remove uppercase + letter-spacing captions.
- **CI guards at the end.** No raw `font-size: Npx` outside `tokens.css`, hex colors only in `tokens.css`, zero `!important`.

## Phases
1. **Tokens and base elements (M–L).**
   - Buttons (sm/md/lg, primary/secondary/ghost/danger, nowrap, disabled), inputs 36px with a focus ring, cards (border, radius 12, no shadow), underline tabs, tables, badges, empty and error states, skeleton, reduced motion.
   - No JSX changes.
2. **App shell (M).**
   - Top bar 56px, white, bottom border: logo + context, search, bell, and a new `AvatarMenu` (profile, language, logout).
   - Sidebar 240px with 32px items; active item uses surface-brand with #066a72 text. Remove the duplicate personal items.
   - Logged-out bar: ghost Войти + primary Регистрация.
3. **Catalog (`CoursesPage`) (M).**
   - Page header; filters on their own row; grid `minmax(280px, 1fr)`.
   - Card: 16:9 cover, 2-line title, one meta line; the whole card is the link; enrolled cards get a progress bar.
   - Skeleton, empty and error states.
4. **My learning + course page (M–L).**
   - My learning: one wide Continue card, then a My courses grid; secondary actions go into a ⋯ menu.
   - Course page: breadcrumb, h1, progress and one primary; module rows with status icons.
   - Player and CodeExercise: tokens only, layout unchanged.
5. **Other student screens (M).** Study, Deadlines, Agenda, Assignments, Quizzes, Results, InlineStepQuiz, Discussion, Notifications, Profile. Forms 720px wide, primary button last.
6. **Teacher screens (M–L).** TeacherDashboard (plain stat numbers, an "attention" table), WorkspaceHub, Grading, AuthorTools, MediaUploader, LessonContentEditor, Analytics, Management.
7. **Admin + cleanup (M).**
   - UsersPage: header, filters row, table with 44px rows, row actions in a ⋯ menu.
   - SystemPage, BackupPanel, AdminControl, StudentsPage.
   - Delete `Brand.css` and the legacy aliases; turn on the CI guards.

## Per phase
- Run `npm run lint` and `npm run build`.
- When `messages.json` changes: add the new strings to BOTH catalogs and run `manage.py test accounts.test_localization`.
- Check the result by eye:
  - as student, teacher, admin and logged out;
  - in ru, kk and en;
  - at 1440, 1024 and 390px;
  - keyboard focus.

## Do not change
Backend APIs, routes, hash URLs, `workspaces.ts` logic, `apiRequest`, permissions, i18n call sites (only add strings), class names that code queries, the player/editor structure, or how authored lesson content is rendered.
