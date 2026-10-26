# Cascade Sentinel — color-only retheme report

## Result

The supplied React/Vite + FastAPI project has been rethemed to the requested Navy/Blue/Steel/Pale/Mist/White palette. Across the existing application source, layout, spacing, typography, components, labels, logic, API calls, backend, and data were left unchanged. The existing source-code edits are color values only; one map risk red and one chart risk red received lightness-only adjustments to remain legible. `frontend/dist/` was rebuilt.

The complete selector/property ledger is [theme-color-values.csv](theme-color-values.csv); it records the old/new value and source line for each CSS color declaration, plus the JSX and HTML color edits.

## Change table

| File and line | Old color/value | New color/value | Purpose |
|---|---|---|---|
| `frontend/src/styles.css:1` | Dark palette tokens: `#090E15`, `#101720`, `#141E29`, `#1A2632`, `#E5EDF6`, `#8E9BAA`, `#24313D`, cyan `#65C8D0`, indigo `#9A9EF8` | `#0F324E` Navy, `#105DC9` Blue, `#9BB5D6` Steel, `#D0DCE8` Pale, `#F0F4F7` Mist, `#FFFFFF` White; muted Navy at `70%` opacity | Root palette tokens and neutral surfaces |
| `frontend/src/styles.css:2–6` | Existing dark surfaces, pale-on-dark text, neon chart/action accents, and dark gridlines | Navy/White/Mist/Pale role tokens; Blue primary actions and rainfall series; Steel accents/forecast series; opacity-derived semantic tints; Navy chart risk text | Recolors existing components and responsive rules without changing layout or behavior. Exact per-selector values are in the CSV. |
| `frontend/src/styles.css:2, 5–6, 8–10` | No disabled background, top-bar fill, scrollbar palette, top-bar focus override, or table-row hover color in those source declarations | Disabled fill Pale with Navy text; top bar Navy; scrollbar Steel on Mist; 2px Blue focus with White override on Navy; selected/hover table Mist | Added only color-valued declarations/rules needed for requested states |
| `frontend/src/main.jsx:318` | `#f16d64` | `#F16E65` | Map risk red; a hue-preserving, minimal lightness increase (Navy label contrast is 4.51:1) |
| `frontend/index.html:6` | `#0b1018` | `#0F324E` | Browser theme-color metadata |
| `frontend/dist/index-C3Mptxtg.css`, `frontend/dist/index-CPBbZ09l.js`, `frontend/dist/index.html` | Previous Vite output | Regenerated from the updated source | Rebuilt production assets served by FastAPI |

The CSV also lists newly defined root palette/semantic variables and all color-only state declarations. A structural stylesheet diff found **zero non-color CSS declaration changes**. The source diff in `main.jsx` is one map color literal; the HTML diff is only the theme-color value. An old-hex grep found no obsolete neutral/cyan/indigo theme literals; remaining shared literals are preserved semantic colors (success/warning/alert, the red risk-dot fill, and its dark outline).

## Semantic colors and accessibility

WATCH, PREPARE, ALERT, ESCALATE, warning/error/success/danger states, ledger integrity cues, hypothesis colors, and map risk meaning remain semantic and labeled. Semantic red values were adjusted only in lightness where needed; hues were retained. No custom skeleton, accordion, tooltip, popover, toast, or mobile-drawer components exist in the supplied app, so none were added.

Contrast checks for representative roles: muted Navy on Mist `4.69:1`; Navy on the adjusted red map cell `4.51:1`; Steel on Navy `6.29:1`; White on Blue `6.12:1`. Semantic text-on-tint checks were at least `6.22:1`. Interactive controls retain visible focus styling; focus color is Blue on light surfaces and White within the Navy sidebar/top bar.

## Build, runtime, and tests

- `npm run build`: **passed**; Vite generated `frontend/dist/`.
- Port `8000` smoke test: **passed** for `/`, `/api/health`, `/manus-routes.json`, and the built CSS palette. The route manifest returned HTTP 200 JSON. The WebDev preview is also running on its configured port 3000.
- Protected paths `app.py`, `web_app.py`, `run.py`, `src/`, `data/`, `tests/`, and `requirements.txt`: **byte-for-byte unchanged** relative to the supplied archive.
- Python pytest suite: **38 passed, 2 failed**. Both failures reproduced on a pristine extraction of the original archive: `test_live_adapter_offline_resilience` expects 241 hourly rows but returns 240 for the current date, and `test_historical_replay_suite` expects the 2023 quiet replay to be WATCH but receives PREPARE. These pre-existing failures were not altered because the request prohibits backend, data, and test changes. Test runs were isolated from the project data.

The requested 1440/1024/390 px × Live/Replay/Offline matrix and complete control-flow matrix were not exhaustively exercised; all seven tabs were captured before/after in one browser viewport. The ledger acknowledgement action was intentionally not triggered because it would write project data.

## Before/after screenshots

Clean browser captures for every dashboard tab are included below. The screenshots use the same desktop browser viewport for before/after comparison; the additional overview desktop capture is not included because the screenshot utility annotated it with diagnostic overlays.

| Tab | Before | After |
|---|---|---|
| Overview | [Before](theme-screenshots/before/overview.webp) | [After](theme-screenshots/after/overview.webp) |
| Grid map | [Before](theme-screenshots/before/map.webp) | [After](theme-screenshots/after/map.webp) |
| Evidence | [Before](theme-screenshots/before/evidence.webp) | [After](theme-screenshots/after/evidence.webp) |
| Decision & policy | [Before](theme-screenshots/before/policy.webp) | [After](theme-screenshots/after/policy.webp) |
| Why-ledger | [Before](theme-screenshots/before/ledger.webp) | [After](theme-screenshots/after/ledger.webp) |
| Replay lab | [Before](theme-screenshots/before/replay.webp) | [After](theme-screenshots/after/replay.webp) |
| Method | [Before](theme-screenshots/before/method.webp) | [After](theme-screenshots/after/method.webp) |

## Scope confirmation

**Within the pre-existing application source, nothing except color values changed; layout, behavior, APIs, backend, data, and tests are unchanged.** Supporting additions are the WebDev route manifest, the required project TODO, this audit, and the requested screenshots.
