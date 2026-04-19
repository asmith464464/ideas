# Ideas Repo — Claude Guide

## What This Repo Is

A Jekyll site that publishes quantitative trading strategy research. Each "idea" is a self-contained backtest with a writeup. The site is built from structured source artifacts, not hand-written posts.

---

## How Blog Posts Are Generated

**Never write directly to `_posts/`**. Posts are assembled by `build.py` from source files in `docs/ideas/`.

### Pipeline

```
docs/ideas/{id}-{slug}/
  config.yaml              ← metadata (id, name, slug, tags, params)
  report.md                ← content with {{ tag }} placeholders
  artifacts/
    results.json           ← key metrics (numbers only)
    charts/
      *.html               ← Plotly charts (written by generate_report.py)

  ↓  python build.py --idea {slug}  ↓

_posts/{published_date}-{slug}.md  ← assembled output (DO NOT EDIT)
```

### Tag Syntax in report.md

Tags are resolved by `preprocessor/tag_resolver.py`:

| Tag | Output |
|-----|--------|
| `{{ metric:key_name }}` | Stat card from `results.json` |
| `{{ metric:key_name \| label=My Label \| suffix=% }}` | Stat card with custom label/suffix |
| `{{ metric:key_name \| positive_is_good=false }}` | Negative value shown as green |
| `{{ chart:chart_id }}` | Plotly chart from `artifacts/charts/{chart_id}.html` |
| `{{ chart:chart_id \| caption=My caption }}` | Chart with caption |
| `{{ metric_table }}` | Full table of all results.json values |
| `{{ signal_table \| rows=20 }}` | Signal table from `signal_table.json` |

Keys ending in `_pct` automatically get a `%` suffix. `max_drawdown_pct` and `annualised_volatility_pct` are treated as negative-good by default.

### config.yaml Required Fields

```yaml
id: '006'
name: 'Human-readable title'
slug: '006-my-slug'
version: '1.0.0'
status: published          # or: draft
published_date: '2026-04-19'

tags:
  - factor-investing
  - equities

date_range:
  start: '2012-01-01'
  end: '2026-04-18'
```

---

## Directory Layout for Each Idea

```
research/ideas/{slug}/
  explore.py              ← main backtest script (standalone, runnable)
  generate_report.py      ← produces artifacts/ and triggers build.py
  notes.md                ← iteration log (update after each run)
  cache/                  ← local cache (gitignored)

docs/ideas/{slug}/
  config.yaml
  report.md
  artifacts/
    results.json
    charts/*.html
```

### generate_report.py Pattern

Each `generate_report.py`:
1. Imports or re-runs the backtest from `explore.py` (using importlib, not package import — the slug has hyphens)
2. Writes `artifacts/results.json` with all key metrics as flat numbers
3. Writes each chart as a standalone Plotly HTML fragment via `pio.to_html(fig, full_html=False, include_plotlyjs="cdn")`
4. Prints a reminder to run `python build.py --idea {slug}`

Run from repo root:
```bash
python research/ideas/{slug}/generate_report.py
python build.py --idea {slug}
```

### Plotly Chart Style

Use consistent colours and layout across ideas:

```python
import plotly.io as pio

_LAYOUT = dict(
    template="plotly_white",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#1a1a2e"),
)

BLUE   = "#1a56db"
GREEN  = "#16a34a"
RED    = "#dc2626"
AMBER  = "#d97706"
GREY   = "#9ca3af"

def _write(fig, name, charts_dir):
    (charts_dir / f"{name}.html").write_text(
        pio.to_html(fig, full_html=False, include_plotlyjs="cdn"), encoding="utf-8"
    )
```

---

## Iteration Workflow

When developing a new idea:

1. **Build and iterate** in `research/ideas/{slug}/explore.py`
2. **Log results** in `research/ideas/{slug}/notes.md` after each meaningful run
3. **When publishing**, run `generate_report.py` to produce artifacts, then `build.py`
4. **Never** hand-edit files in `_posts/` — they are generated output

---

## Existing Ideas

| ID | Slug | Status |
|----|------|--------|
| 001 | 001-time-series-momentum | draft |
| 002 | 002-momentum-ls | draft |
| 003 | 003-deep-momentum | draft |
| 004 | 004-wiki-trends-crypto | published |
| 005 | 005-hurst-pairs-reversion | published |
| 006 | 006-piotroski-fscore | published |
