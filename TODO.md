# TODO

## Application palette and visual roles
- [x] Recolor the whole application to the palette below. COLOR-ONLY change. Layout, spacing, typography, components, text, logic and behavior stay exactly the same.
- [x] Use Navy #0F324E, Blue #105DC9, Steel #9BB5D6, Pale #D0DCE8, Mist #F0F4F7, and White #FFFFFF.
- [x] Page background: Mist #F0F4F7. Cards, panels, inputs, tables, modals: White #FFFFFF.
- [x] Sidebar and top bar: Navy #0F324E, with White text; nav icons/labels White, inactive nav at about 70% opacity; active nav item Blue #105DC9 background with White text.
- [x] Text and headings on light surfaces: Navy #0F324E. Secondary/muted text on light surfaces: Navy at about 70% opacity (never Steel, it fails contrast on light backgrounds).
- [x] Borders, dividers, table lines, gridlines, skeletons, disabled backgrounds: Pale #D0DCE8.
- [x] Hover/selected row backgrounds, accordion headers, chips, table header fill: Pale #D0DCE8 or Mist #F0F4F7.
- [x] Primary actions (buttons, links, sliders, toggles, checkboxes, radio, focus rings, active tab underline, selected cell on map): Blue #105DC9, text on Blue is White. Button hover: Navy #0F324E.
- [x] Secondary buttons: White background, Blue border and text.
- [x] Steel #9BB5D6: decorative only (secondary chart series, inactive icons, text on the Navy sidebar, scrollbar, subtle accents).
- [x] Neutral chart elements: rainfall bars and primary lines Blue, secondary series Steel, axes/gridlines/ticks Pale and Navy at 70%, chart backgrounds White, tooltips Navy with White text.

## Semantic colors, states, and accessibility
- [x] Action ladder colors: WATCH, PREPARE, ALERT, ESCALATE must stay four clearly different hues with text labels (keep the existing hues).
- [x] Keep risk, warning, error, success, danger buttons and the verified/failed ledger badge semantic colors unchanged.
- [x] Keep hypothesis colors (NOISE, SENSOR_FAIL, ISOLATED, CASCADE) and any "now"/threshold/horizon reference lines unchanged.
- [x] If any semantic color is hard to read on the new backgrounds, adjust only its lightness, never its hue.
- [x] Map cell risk colors keep their risk meaning; selected-cell outline is Blue.
- [x] Cover every state: hover, focus, active, disabled, selected, empty/loading/error states, skeletons, accordions open/closed, tooltips, popovers, tables, chips, toasts, mobile drawer. (Existing states are color-mapped; no skeleton/accordion/custom tooltip/popover/toast/drawer components exist in the supplied application, and none were added.)
- [x] All text at least 4.5:1 against its background (large text 3:1). Navy on Mist/White, White on Navy, White on Blue all pass; never put Steel or Pale as text on light surfaces.
- [x] Focus ring visible on every interactive element: 2 px Blue outline (White on Navy surfaces).
- [x] Information is never carried by color alone.

## Strict change scope and affected files
- [x] Change all color values in styles.css (reformat nothing else), CSS variables if present (define a single :root variable set for the palette and reuse it everywhere).
- [x] Change inline style colors and hardcoded hex/rgb/hsl/named colors in main.jsx, including SVG fill/stroke, chart colors, tooltip colors, scrollbar, selection, focus outlines.
- [x] Update vite/index.html theme-color and meta tags if present.
- [x] Do not change layout, spacing, sizes, fonts, component order, labels, text, tabs, API calls, state, handlers, backend, data, tests.
- [x] Add no dependencies, gradients, shadows, animations or new CSS rules beyond color properties.
- [x] Use no new color outside this palette (except the kept semantic colors above); derive tints only via opacity.

## Verification and delivery evidence
- [x] List every file and line changed: file | old color | new color (grep first for every color definition and confirm no leftover old-theme colors remain, except the kept semantic ones). See `reports/theme-color-change.md` and `reports/theme-color-values.csv`.
- [x] Confirm the diff contains only color values. Structural CSS audit: zero non-color declaration changes; backend/data/tests are unchanged.
- [ ] npm run build passes; existing tests pass; backend/src/data/tests diff is empty. Build passes and protected paths are unchanged; pytest had 38 passes and two failures, both reproduced on the untouched archive: 241-row live adapter expectation returned 240, and 2023 quiet replay expected WATCH but returned PREPARE.
- [ ] Open every tab at 1440, 1024 and 390 px in Live, Replay and Offline modes. Check hover/focus/disabled/error/empty states, charts, map, tables, ledger and the confirm flow. Zero console errors, no unreadable text, no invisible chart elements. Seven tabs were captured before/after in the same browser viewport; the full 3-width × 3-mode matrix and all state combinations were not exhaustively exercised.
- [ ] Click through every control (mode, event, date, cell, thresholds, acknowledge, ledger download, sensitivity reload, retry) and confirm behavior is unchanged. Navigation across all tabs was checked; the full control matrix was not exhaustively exercised, and the acknowledgement flow was not triggered to avoid modifying local ledger data.
- [x] Rebuild frontend/dist so the app on port 8000 shows the new theme. Build passed and port-8000 smoke test confirmed the served production CSS palette.
- [x] Provide a change table, before/after screenshots of every tab, and a one-line confirmation that nothing except color values changed. See `reports/theme-color-change.md` and `reports/theme-screenshots/`.
