import json
import re
from pathlib import Path

from preprocessor.html_components import (
    render_chart,
    render_metric,
    render_metric_table,
    render_placeholder,
    render_signal_table,
    NEGATIVE_GOOD_KEYS,
)

TAG_PATTERN = re.compile(r'^\s*\{\{\s*(.+?)\s*\}\}\s*$', re.MULTILINE)


class TagResolver:

    def __init__(self, idea_dir: Path, config: dict):
        self.idea_dir  = idea_dir
        self.config    = config
        self.slug      = config['slug']
        self.artifacts = idea_dir / 'artifacts'
        self._results  = self._load_json('results.json')
        self._signals  = self._load_json('signal_table.json')

    def resolve(self, markdown: str) -> str:
        return TAG_PATTERN.sub(self._replace, markdown)

    def _replace(self, match: re.Match) -> str:
        inner = match.group(1)
        try:
            return self._dispatch(inner)
        except Exception as e:
            return self._placeholder(f"error resolving tag '{inner}': {e}")

    def _dispatch(self, inner: str) -> str:
        tag_type, opts = _parse_tag(inner)
        if tag_type == 'metric':
            return self._render_metric(opts)
        elif tag_type == 'chart':
            return self._render_chart(opts)
        elif tag_type == 'metric_table':
            return self._render_metric_table()
        elif tag_type == 'signal_table':
            return self._render_signal_table(opts)
        else:
            return self._placeholder(f"unknown tag type: {tag_type}")

    def _render_metric(self, opts: dict) -> str:
        key = opts.get('key')
        if not key:
            return self._placeholder("metric tag missing key")
        if self._results is None:
            return self._placeholder(f"results.json not found")
        if key not in self._results:
            return self._placeholder(f"key '{key}' not in results.json")

        value           = float(self._results[key])
        label           = opts.get('label')
        decimals        = int(opts.get('decimals', 2))
        suffix          = opts.get('suffix')
        pig_raw         = opts.get('positive_is_good', 'true')
        positive_is_good = key not in NEGATIVE_GOOD_KEYS if pig_raw == 'true' else pig_raw != 'false'

        return render_metric(
            key=key,
            value=value,
            label=label,
            decimals=decimals,
            suffix=suffix,
            positive_is_good=positive_is_good,
        )

    def _render_chart(self, opts: dict) -> str:
        chart_id = opts.get('chart_id')
        if not chart_id:
            return self._placeholder("chart tag missing chart_id")
        chart_path = self.artifacts / 'charts' / f'{chart_id}.html'
        if not chart_path.exists():
            return self._placeholder(f"chart '{chart_id}.html' not found")
        chart_html = chart_path.read_text()
        caption    = opts.get('caption')
        return render_chart(chart_id=chart_id, chart_html=chart_html, caption=caption)

    def _render_metric_table(self) -> str:
        if self._results is None:
            return self._placeholder("results.json not found")
        return render_metric_table(self._results)

    def _render_signal_table(self, opts: dict) -> str:
        if self._signals is None:
            return self._placeholder("signal_table.json not found")
        n = int(opts.get('rows', 20))
        return render_signal_table(self._signals, n=n)

    def _load_json(self, filename: str):
        path = self.artifacts / filename
        if not path.exists():
            return None
        return json.loads(path.read_text())

    def _placeholder(self, message: str) -> str:
        return render_placeholder(message, self.slug)


def _parse_tag(inner: str) -> tuple[str, dict]:
    parts = [p.strip() for p in inner.split('|')]
    head  = parts[0]
    opts  = {}

    if ':' in head:
        tag_type, key_val = head.split(':', 1)
        tag_type = tag_type.strip()
        key_val  = key_val.strip()
        if tag_type == 'metric':
            opts['key'] = key_val
        elif tag_type == 'chart':
            opts['chart_id'] = key_val
    else:
        tag_type = head.strip()

    for part in parts[1:]:
        if '=' in part:
            k, v = part.split('=', 1)
            opts[k.strip()] = v.strip().strip('"').strip("'")

    return tag_type, opts
