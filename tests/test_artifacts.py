import json
import tempfile
from pathlib import Path

import pytest

from preprocessor.tag_resolver import TagResolver, _parse_tag


@pytest.fixture
def mock_idea_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        idea_dir = Path(tmpdir)
        artifacts = idea_dir / 'artifacts'
        charts    = artifacts / 'charts'
        charts.mkdir(parents=True)

        results = {
            'sharpe_ratio':              1.43,
            'total_return_pct':          34.2,
            'annualised_return_pct':     8.1,
            'annualised_volatility_pct': 12.5,
            'sortino_ratio':             1.8,
            'max_drawdown_pct':         -18.3,
            'calmar_ratio':              0.44,
            'win_rate_pct':              54.0,
            'avg_trade_return_pct':      0.05,
            'num_trades':                48,
            'benchmark_return_pct':      220.0,
            'information_ratio':         0.31,
        }
        (artifacts / 'results.json').write_text(json.dumps(results))

        signals = [
            {'date': '2024-01-31', 'ticker': 'SPY', 'signal': 1, 'return': 0.0083},
            {'date': '2024-02-29', 'ticker': 'SPY', 'signal': -1, 'return': -0.0021},
        ]
        (artifacts / 'signal_table.json').write_text(json.dumps(signals))

        (charts / 'equity_curve.html').write_text('<div>chart content</div>')

        yield idea_dir


@pytest.fixture
def config():
    return {'slug': 'test-idea', 'name': 'Test Idea'}


def test_metric_tag_renders_stat_card(mock_idea_dir, config):
    resolver = TagResolver(mock_idea_dir, config)
    md = '{{ metric: sharpe_ratio }}'
    result = resolver.resolve(md)
    assert 'stat-value' in result
    assert 'stat-label' in result
    assert '1.43' in result


def test_metric_tag_with_options(mock_idea_dir, config):
    resolver = TagResolver(mock_idea_dir, config)
    md = '{{ metric: sharpe_ratio | label="Sharpe ratio" | decimals=2 }}'
    result = resolver.resolve(md)
    assert 'Sharpe ratio' in result
    assert '1.43' in result


def test_chart_tag_renders_wrapper_with_content(mock_idea_dir, config):
    resolver = TagResolver(mock_idea_dir, config)
    md = '{{ chart: equity_curve }}'
    result = resolver.resolve(md)
    assert 'chart-wrapper' in result
    assert 'chart content' in result


def test_chart_tag_with_caption(mock_idea_dir, config):
    resolver = TagResolver(mock_idea_dir, config)
    md = '{{ chart: equity_curve | caption="Strategy vs SPY" }}'
    result = resolver.resolve(md)
    assert 'chart-caption' in result
    assert 'Strategy vs SPY' in result


def test_missing_artifact_produces_placeholder_no_exception(mock_idea_dir, config):
    resolver = TagResolver(mock_idea_dir, config)
    md = '{{ chart: nonexistent_chart }}'
    result = resolver.resolve(md)
    assert 'artifact-placeholder' in result
    assert '{{' not in result


def test_missing_results_json_produces_placeholder(config):
    with tempfile.TemporaryDirectory() as tmpdir:
        idea_dir = Path(tmpdir)
        (idea_dir / 'artifacts').mkdir()
        resolver = TagResolver(idea_dir, config)
        result = resolver.resolve('{{ metric: sharpe_ratio }}')
        assert 'artifact-placeholder' in result


def test_metric_table_renders_all_keys(mock_idea_dir, config):
    resolver = TagResolver(mock_idea_dir, config)
    result = resolver.resolve('{{ metric_table }}')
    assert 'metric-table' in result
    assert 'Sharpe Ratio' in result
    assert 'Total Return' in result


def test_signal_table_renders_rows(mock_idea_dir, config):
    resolver = TagResolver(mock_idea_dir, config)
    result = resolver.resolve('{{ signal_table | rows=20 }}')
    assert 'signal-table' in result


def test_parse_tag_metric_basic():
    tag_type, opts = _parse_tag('metric: sharpe_ratio')
    assert tag_type == 'metric'
    assert opts['key'] == 'sharpe_ratio'


def test_parse_tag_metric_with_options():
    tag_type, opts = _parse_tag('metric: sharpe_ratio | label="Sharpe ratio" | decimals=2')
    assert tag_type == 'metric'
    assert opts['key'] == 'sharpe_ratio'
    assert opts['label'] == 'Sharpe ratio'
    assert opts['decimals'] == '2'


def test_parse_tag_chart():
    tag_type, opts = _parse_tag('chart: equity_curve | caption="vs SPY"')
    assert tag_type == 'chart'
    assert opts['chart_id'] == 'equity_curve'
    assert opts['caption'] == 'vs SPY'


def test_parse_tag_metric_table():
    tag_type, opts = _parse_tag('metric_table')
    assert tag_type == 'metric_table'
    assert opts == {}


def test_parse_tag_signal_table_with_rows():
    tag_type, opts = _parse_tag('signal_table | rows=20')
    assert tag_type == 'signal_table'
    assert opts['rows'] == '20'


def test_parse_tag_quoted_single_quotes():
    tag_type, opts = _parse_tag("metric: sharpe_ratio | label='My Label'")
    assert opts['label'] == 'My Label'
