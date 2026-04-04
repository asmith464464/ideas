NEGATIVE_GOOD_KEYS = {'max_drawdown_pct', 'annualised_volatility_pct'}


def _value_class(value: float, positive_is_good: bool) -> str:
    if value == 0:
        return ''
    if (value > 0) == positive_is_good:
        return 'positive'
    return 'negative'


def _humanise_key(key: str) -> str:
    return key.replace('_', ' ').title()


def _auto_suffix(key: str) -> str:
    return '%' if key.endswith('_pct') else ''


def render_metric(
    key: str,
    value: float,
    label: str = None,
    decimals: int = 2,
    suffix: str = None,
    positive_is_good: bool = True,
) -> str:
    display_label = label if label is not None else _humanise_key(key)
    display_suffix = suffix if suffix is not None else _auto_suffix(key)
    css_class = _value_class(value, positive_is_good)
    value_str = f"{value:.{decimals}f}{display_suffix}"
    class_attr = f' class="stat-value {css_class}"' if css_class else ' class="stat-value"'
    return (
        '<div class="stat-card">\n'
        f'  <div class="stat-label">{display_label}</div>\n'
        f'  <div{class_attr}>{value_str}</div>\n'
        '</div>'
    )


def render_chart(chart_id: str, chart_html: str, caption: str = None) -> str:
    caption_block = ''
    if caption:
        caption_block = f'\n  <p class="chart-caption">{caption}</p>'
    return (
        '<div class="chart-wrapper">\n'
        f'  {chart_html}{caption_block}\n'
        '</div>'
    )


def render_metric_table(results: dict) -> str:
    rows = []
    for key, value in results.items():
        label = _humanise_key(key)
        suffix = _auto_suffix(key)
        positive_is_good = key not in NEGATIVE_GOOD_KEYS
        css_class = _value_class(float(value), positive_is_good)
        class_attr = f' class="metric-value {css_class}"' if css_class else ' class="metric-value"'
        try:
            value_str = f"{float(value):.2f}{suffix}"
        except (TypeError, ValueError):
            value_str = str(value)
        rows.append(
            f'    <tr>\n'
            f'      <td class="metric-key">{label}</td>\n'
            f'      <td{class_attr}>{value_str}</td>\n'
            f'    </tr>'
        )
    return (
        '<table class="metric-table">\n'
        '  <tbody>\n'
        + '\n'.join(rows) + '\n'
        '  </tbody>\n'
        '</table>'
    )


def render_signal_table(rows: list[dict], n: int = 20) -> str:
    display_rows = rows[-n:] if len(rows) > n else rows
    if not display_rows:
        return '<div class="signal-table-wrapper"><p>No signal data available.</p></div>'

    headers = list(display_rows[0].keys())
    header_cells = ''.join(f'<th>{h.replace("_", " ").title()}</th>' for h in headers)

    body_rows = []
    for row in display_rows:
        cells = []
        for h in headers:
            val = row[h]
            if h == 'signal':
                if val == 1 or val == '+1':
                    cells.append('<td class="signal-long">+1</td>')
                elif val == -1 or val == '-1':
                    cells.append('<td class="signal-short">-1</td>')
                else:
                    cells.append(f'<td>{val}</td>')
            elif h in ('return', 'return_pct', 'daily_return'):
                try:
                    fval = float(val) * 100
                    css = 'positive' if fval > 0 else ('negative' if fval < 0 else '')
                    class_attr = f' class="{css}"' if css else ''
                    cells.append(f'<td{class_attr}>{fval:+.2f}%</td>')
                except (TypeError, ValueError):
                    cells.append(f'<td>{val}</td>')
            else:
                cells.append(f'<td>{val}</td>')
        body_rows.append('      <tr>' + ''.join(cells) + '</tr>')

    return (
        '<div class="signal-table-wrapper">\n'
        '  <table class="signal-table">\n'
        '    <thead>\n'
        f'      <tr>{header_cells}</tr>\n'
        '    </thead>\n'
        '    <tbody>\n'
        + '\n'.join(body_rows) + '\n'
        '    </tbody>\n'
        '  </table>\n'
        '</div>'
    )


def render_placeholder(message: str, slug: str) -> str:
    return (
        '<div class="artifact-placeholder">\n'
        f'  artifact not yet generated — run: python run_research.py --idea {slug}\n'
        '</div>'
    )
