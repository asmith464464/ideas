import argparse
import importlib
import re
import sys
import time
from pathlib import Path

import yaml


def _load_config(idea_dir: Path) -> dict:
    return yaml.safe_load((idea_dir / 'config.yaml').read_text())


def _discover_ideas(docs_dir: Path) -> list[dict]:
    ideas = []
    for config_path in sorted(docs_dir.glob('*/config.yaml')):
        config = _load_config(config_path.parent)
        config['_idea_dir'] = config_path.parent
        ideas.append(config)
    return ideas


def _slug_to_class_name(slug: str) -> str:
    without_prefix = re.sub(r'^\d+-', '', slug)
    return ''.join(word.capitalize() for word in without_prefix.split('-'))


def _run_idea(config: dict, no_cache: bool) -> dict:
    slug     = config['slug']
    idea_dir = config['_idea_dir']

    module_path = f"research.ideas.{slug}.strategy"
    module      = importlib.import_module(module_path)
    class_name  = _slug_to_class_name(slug)
    cls         = getattr(module, class_name)

    if no_cache:
        from data.fetchers.yfinance_fetcher import YFinanceFetcher
        YFinanceFetcher.__init__.__defaults__ = (True,)

    strategy = cls(idea_dir=idea_dir, config=config)
    t0 = time.time()
    strategy.run()
    elapsed = time.time() - t0

    results_path = idea_dir / 'artifacts' / 'results.json'
    import json
    results = json.loads(results_path.read_text())

    return {
        'name':          config['name'],
        'sharpe':        results.get('sharpe_ratio', float('nan')),
        'total_return':  results.get('total_return_pct', float('nan')),
        'max_drawdown':  results.get('max_drawdown_pct', float('nan')),
        'elapsed':       elapsed,
    }


def _print_summary(rows: list[dict]) -> None:
    print()
    header = f"{'Idea':<40} {'Sharpe':>8} {'Return%':>10} {'MaxDD%':>10} {'Time':>7}"
    print(header)
    print('-' * len(header))
    for r in rows:
        print(
            f"{r['name']:<40} "
            f"{r['sharpe']:>8.2f} "
            f"{r['total_return']:>10.1f} "
            f"{r['max_drawdown']:>10.1f} "
            f"{r['elapsed']:>6.1f}s"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description='Run research pipeline')
    group  = parser.add_mutually_exclusive_group()
    group.add_argument('--all',  action='store_true')
    group.add_argument('--idea', type=str)
    group.add_argument('--tag',  type=str)
    parser.add_argument('--no-cache', action='store_true')
    args = parser.parse_args()

    docs_dir = Path('docs/ideas')
    ideas    = _discover_ideas(docs_dir)

    if args.idea:
        ideas = [c for c in ideas if c['slug'] == args.idea]
    elif args.tag:
        ideas = [c for c in ideas if args.tag in c.get('tags', [])]
    elif not args.all:
        parser.print_help()
        sys.exit(1)

    if not ideas:
        print('No matching ideas found.')
        sys.exit(1)

    summary = []
    for config in ideas:
        print(f"\nRunning: {config['slug']}")
        row = _run_idea(config, no_cache=args.no_cache)
        summary.append(row)

    _print_summary(summary)


if __name__ == '__main__':
    main()
