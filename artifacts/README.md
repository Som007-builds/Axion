# UI evidence

Screenshots and machine-readable checks captured while reviewing the Cobalt Grid
frontend. They are **evidence, not a regression suite** — nothing in CI compares
them.

| Path | What it is |
| :--- | :--- |
| `demo-*.png` | The images used in the root README (research report, graph, contradictions, gaps, timeline, evolution). |
| `audit/desktop-*`, `audit/laptop-*`, `audit/mobile-*`, `audit/small-mobile-*` | Every view at four breakpoints in light and dark themes. |
| `audit/final-*`, `audit/graph-check-*`, `audit/ui-fix-*` | Final interaction checks (sheet, graph node, mobile query, header/ingest form). |
| `audit/*.json` | Playwright audit output: layout measurements, interaction results, console errors. |
| `axion-architecture.html` / `.json` | Standalone architecture diagram and its source data. |

To reproduce the audit, run the frontend against a live API and re-capture with
the same viewport set; the JSON files record the expected dimensions and checks.
