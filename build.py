import argparse
import sys
from datetime import date
from pathlib import Path

import yaml

from preprocessor.tag_resolver import TagResolver


def _load_config(idea_dir: Path) -> dict:
    return yaml.safe_load((idea_dir / 'config.yaml').read_text())


def _discover_ideas(docs_dir: Path) -> list[tuple[Path, dict]]:
    ideas = []
    for config_path in sorted(docs_dir.glob('*/config.yaml')):
        config = _load_config(config_path.parent)
        ideas.append((config_path.parent, config))
    return ideas


def _front_matter(config: dict) -> str:
    tags_yaml = '\n'.join(f'  - {t}' for t in config.get('tags', []))
    dr = config.get('date_range', {})
    return (
        '---\n'
        f'layout: idea\n'
        f'title: "{config["name"]}"\n'
        f'slug: "{config["slug"]}"\n'
        f'idea_id: "{config["id"]}"\n'
        f'version: "{config["version"]}"\n'
        f'status: "{config["status"]}"\n'
        f'tags:\n{tags_yaml}\n'
        f'date_range_start: "{dr.get("start", "")}"\n'
        f'date_range_end: "{dr.get("end", "")}"\n'
        '---\n\n'
    )


def _post_filename(config: dict) -> str:
    pub_date = config.get('published_date', str(date.today()))
    slug     = config['slug']
    return f"{pub_date}-{slug}.md"


def _process_idea(
    idea_dir: Path,
    config: dict,
    posts_dir: Path,
) -> tuple[int, int]:
    report_path = idea_dir / 'report.md'
    if not report_path.exists():
        print(f"  [skip] {config['slug']}: report.md not found")
        return 0, 0

    markdown = report_path.read_text(encoding='utf-8')
    resolver = TagResolver(idea_dir, config)
    resolved = resolver.resolve(markdown)

    from preprocessor.tag_resolver import TAG_PATTERN
    tags_found        = len(TAG_PATTERN.findall(markdown))
    placeholders_used = resolved.count('artifact-placeholder')
    tags_resolved     = tags_found - placeholders_used

    output = _front_matter(config) + resolved
    filename = _post_filename(config)
    (posts_dir / filename).write_text(output, encoding='utf-8')

    return tags_resolved, placeholders_used


def _regenerate_index(ideas: list[tuple[Path, dict]], root: Path) -> None:
    published = [
        (d, c) for d, c in ideas if c.get('status') == 'published'
    ]
    cards = []
    for _, config in published:
        slug = config['slug']
        pub_date = config.get('published_date', '')
        tags = ' '.join(config.get('tags', []))
        cards.append(
            f'<div class="idea-card" data-tags="{tags}">\n'
            f'  <a class="idea-title" href="{{{{ site.baseurl }}}}/{slug}/">'
            f'{config["name"]}</a>\n'
            f'  <div class="idea-meta">{config["id"]} · {pub_date}</div>\n'
            f'</div>\n'
        )
    index_path = root / 'index.html'
    if index_path.exists():
        content = index_path.read_text(encoding='utf-8')
        marker_start = '<!-- IDEAS_START -->'
        marker_end   = '<!-- IDEAS_END -->'
        if marker_start in content and marker_end in content:
            before = content[:content.index(marker_start) + len(marker_start)]
            after  = content[content.index(marker_end):]
            new_content = before + '\n' + ''.join(cards) + after
            index_path.write_text(new_content, encoding='utf-8')


def main() -> None:
    parser = argparse.ArgumentParser(description='Preprocess ideas into Jekyll _posts/')
    parser.add_argument('--idea',            type=str)
    parser.add_argument('--include-drafts',  action='store_true')
    args = parser.parse_args()

    docs_dir  = Path('docs/ideas')
    posts_dir = Path('_posts')
    posts_dir.mkdir(exist_ok=True)

    all_ideas = _discover_ideas(docs_dir)

    if args.idea:
        ideas = [(d, c) for d, c in all_ideas if c['slug'] == args.idea]
    else:
        ideas = all_ideas

    if not args.include_drafts:
        ideas = [(d, c) for d, c in ideas if c.get('status') != 'draft']

    if not ideas and not args.idea:
        print('No published ideas found. Use --include-drafts to include drafts.')
        sys.exit(0)

    total_resolved     = 0
    total_placeholders = 0
    processed          = 0

    for idea_dir, config in ideas:
        print(f"Processing: {config['slug']}")
        resolved, placeholders = _process_idea(idea_dir, config, posts_dir)
        total_resolved     += resolved
        total_placeholders += placeholders
        processed          += 1

    _regenerate_index(all_ideas, Path('.'))

    print(f"\nDone: {processed} idea(s), {total_resolved} tag(s) resolved, "
          f"{total_placeholders} placeholder(s) inserted.")


if __name__ == '__main__':
    main()
