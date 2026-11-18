# BTBS design spec (minimal, "finished" UI)

Source: research of Primer, Geist, Radix Colors, Atlassian, Linear (Nov 2026). Contrast ratios: WCAG 2.x.

## Principles
1. One primary (filled teal) button per view; secondary is the default button.
2. Group with whitespace → borders → shadows. Shadows only for floating things (menus, modals, toasts). Cards: 1px border, no shadow.
3. Never nest bordered surfaces (no card in card).
4. Fixed type tokens only (≤7 sizes, weights 400/500/600). No text below 12px.
5. Neutral UI, teal as accent only (primary action, links, selected, progress).
6. 4px grid for spacing and line heights.
7. Sentence case; button labels never wrap (`white-space: nowrap`), shorten copy instead.
8. Every list/page has loading (skeleton), empty (title + one line + one action), error (specific + recovery) and focus states.
9. Reading text max 72ch, left-aligned.

## Tokens
Font: `"Segoe UI Variable Text", "Segoe UI", -apple-system, BlinkMacSystemFont, "Inter", "Noto Sans", Helvetica, Arial, sans-serif`; mono `ui-monospace, "Cascadia Code", Consolas, "SF Mono", Menlo, monospace`; numbers `tabular-nums`.

| Token | Size/LH | Weight |
|---|---|---|
| display | 36/44 | 600, -0.02em |
| h1 | 28/36 | 600, -0.01em |
| h2 | 20/28 | 600 |
| h3 | 16/24 | 600 |
| body-lg | 16/26 | 400 (lesson text) |
| body | 14/22 | 400, labels 500 |
| small | 13/20 | 400 |
| caption | 12/16 | 500 |

Spacing: 4, 8, 12, 16, 20, 24, 32, 40, 48, 64. Radii: 6 (controls, badges), 12 (cards, menus, modals), 16 (sheets, hero), 999 (pills). Borders 1px only.
Shadows: sm `0 1px 2px rgba(16,37,66,.06)`; md `0 4px 12px rgba(16,37,66,.08), 0 1px 3px rgba(16,37,66,.06)`; lg `0 16px 40px rgba(16,37,66,.16)`.

Colors: bg #f5f7fa · surface #fff · surface-subtle #f0f3f7 · surface-brand #e8f6f6 · border #e3e9ef · border-strong #c9d3de · text #182b43 · text-muted #5b6b80 (old #65758a fails AA on canvas) · primary #087f88 · primary-hover #066a72 · primary text on soft teal #066a72 · cyan #38c3c9 never as text (fills only) · navy #102542, muted on navy #9fb0c3 · focus ring `0 0 0 3px rgba(8,127,136,.35)` + 1px #087f88 · success #067647/#ecfdf3 · warning #b54708/#fffaeb · danger #b42318/#fef3f2.

## Components
- Buttons: sm 28px (0 10px, 13px), md 36px (0 14px, 14px/500), lg 44px (0 20px, 15px/500, player/hero only). Primary teal; secondary white + border-strong; ghost transparent, hover surface-subtle; danger = secondary with danger text, solid red only in confirm dialogs. Primary last/right in groups. Loading keeps width.
- Inputs: 36px, 0 12px, border-strong, radius 6, hover #a9b6c5, focus teal border + ring; label above 13px/500; help/error below 12–13px with icon.
- Cards: white, border, radius 12, padding 20–24 (16 dense), no shadow; clickable → border-strong + shadow-sm on hover 150ms. No colored header bands.
- Tables: row bottom borders only, rows 44px (36 dense), header 36px surface-subtle 12px/500 muted, numbers right + tabular; row actions in ⋯ menu.
- Tabs: underline, 14px/500 muted, active ink + 2px teal underline, 36px, 1px bottom border.
- Badges: 20–22px pill, caption, soft status bg + dark text; ≤1 per row.
- Empty states: optional 48px icon, h3, one muted line, one button; centered, 48px padding.
- Toasts bottom-right, shadow-md; inline alerts soft status bg.
- Modals 480/640px, radius 12, shadow-lg, backdrop rgba(16,37,66,.4), actions right (ghost Cancel, primary).
- Top bar 56px white + bottom border; logo left, search, avatar menu (profile, language, logout). Teacher/admin sidebar 240px, items 32px, active surface-brand + #066a72 text. Students: 3–5 top items.
- Page header: breadcrumb (13px muted) → h1 → one muted line; right: one primary + ⋯ menu; filters on their own row.

## Layout
Dashboards max 1280px, gutters 24 (16 below 1280); forms 720px; reading 72ch; auth 400px. Breakpoints 544/768/1012/1280. Grid gap 24; catalog `repeat(auto-fill, minmax(280px, 1fr))`. Dense (teacher/admin): 14px body, 36px rows, 16px padding; student/reading: 16px body, 24px padding, 48px section gaps. Max 1 primary + 2 secondary visible; rest in ⋯.

## Motion
Hover 100ms; menus 150/100ms; modals/toasts 250/200ms; easing `cubic-bezier(0.2,0,0,1)`, exits `cubic-bezier(0.3,0,0.8,0.15)`; only opacity/transform; respect `prefers-reduced-motion`. Skeletons for lists/pages; spinners only inside buttons.

## Learning patterns
Catalog card: 16:9 cover or flat tile, h3 (2 lines), one meta line, whole card is the link, 4px progress bar if enrolled. Student home: one wide "Continue" card (course, next lesson, "Lesson 4 of 12", progress, primary Continue) then "My courses" grid. Progress: 6–8px pill, teal/cyan fill, always with a text label. Lesson status icons: empty circle / half / teal check / lock.

## Anti-patterns to remove
Several filled buttons in a row; caps/wrapping labels; cards in cards; shadows on every card; mixed radii; colored header bands, gradients, emoji as icons; arbitrary font sizes; teal/cyan text on white or soft teal; grey text on grey canvas; gridded tables; raw "No data", full-page spinners, browser dialogs; missing focus/hover/disabled states; flags/long toolbars in the top bar; spacing off the 4px scale.
