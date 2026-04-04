import json
import math
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


SLUG     = '001-time-series-momentum'
IDEA_DIR = Path('docs/ideas') / SLUG
SHORT_CONFIG = {
    'id':      '001',
    'name':    'Time-series momentum',
    'slug':    SLUG,
    'version': '0.1.0',
    'status':  'draft',
    'tags':    ['momentum', 'equities', 'daily'],
    'universe': ['SPY', 'QQQ'],
    'date_range': {'start': '2024-01-01', 'end': '2024-04-01'},
    'benchmark':           'SPY',
    'risk_free_rate':       0.0,
    'lookback_days':        63,
    'skip_days':            5,
    'rebalance':           'monthly',
    'transaction_cost_bps': 5,
}

REQUIRED_KEYS = {
    'total_return_pct',
    'annualised_return_pct',
    'annualised_volatility_pct',
    'sharpe_ratio',
    'sortino_ratio',
    'max_drawdown_pct',
    'calmar_ratio',
    'win_rate_pct',
    'avg_trade_return_pct',
    'num_trades',
    'benchmark_return_pct',
    'information_ratio',
}


@pytest.fixture(scope='module')
def run_strategy(tmp_path_factory):
    import importlib
    tmp = tmp_path_factory.mktemp('idea')
    (tmp / 'artifacts' / 'charts').mkdir(parents=True)

    module = importlib.import_module(f'research.ideas.{SLUG}.strategy')
    cls = getattr(module, 'TimeSeriesMomentum')

    strategy = cls(idea_dir=tmp, config=SHORT_CONFIG)
    strategy.run()
    return tmp


def test_run_completes_without_exception(run_strategy):
    assert run_strategy.exists()


def test_results_json_exists_with_all_keys(run_strategy):
    results_path = run_strategy / 'artifacts' / 'results.json'
    assert results_path.exists()
    results = json.loads(results_path.read_text())
    assert set(results.keys()) == REQUIRED_KEYS


def test_equity_curve_html_exists_and_nonempty(run_strategy):
    chart_path = run_strategy / 'artifacts' / 'charts' / 'equity_curve.html'
    assert chart_path.exists()
    assert len(chart_path.read_text()) > 100


def test_signal_table_has_rows(run_strategy):
    sig_path = run_strategy / 'artifacts' / 'signal_table.json'
    assert sig_path.exists()
    rows = json.loads(sig_path.read_text())
    assert len(rows) >= 1


def test_sharpe_ratio_is_finite_float(run_strategy):
    results = json.loads((run_strategy / 'artifacts' / 'results.json').read_text())
    sharpe = results['sharpe_ratio']
    assert isinstance(sharpe, float)
    assert math.isfinite(sharpe)


def test_build_produces_post_with_no_unresolved_tags(tmp_path):
    import shutil
    from build import _process_idea

    posts_dir = tmp_path / '_posts'
    posts_dir.mkdir()

    config_path = IDEA_DIR / 'config.yaml'
    if not config_path.exists():
        pytest.skip('config.yaml not found — run from repo root')

    config = yaml.safe_load(config_path.read_text())

    _process_idea(IDEA_DIR, config, posts_dir)

    written = list(posts_dir.glob('*.md'))
    assert len(written) == 1

    content = written[0].read_text()
    assert '{{' not in content
