#!/usr/bin/env python3
"""Check the built site's local navigation, assets, headings and structured metadata.

No network requests: this checks the artifact that will be deployed, including all
pages generated from task templates. Run after `bun run build`.
"""
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit
import json
import sys

SITE = 'https://businessbench.org'
DIST = Path(__file__).resolve().parents[1] / 'dist'

class Page(HTMLParser):
    def __init__(self, path):
        super().__init__(convert_charrefs=True)
        self.path = path
        self.ids = []
        self.links = []
        self.h1 = 0
        self.title = ''
        self.canonical = []
        self.description = []
        self.errors = []
        self.in_title = False
        self.in_head = False
        self.title_count = 0
        self.in_json = False
        self.json_parts = []
        self.feed(path.read_text())

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get('id'):
            self.ids.append(attrs['id'])
        if tag == 'h1':
            self.h1 += 1
        if tag == 'head':
            self.in_head = True
        if tag == 'title' and self.in_head:
            self.in_title = True
            self.title_count += 1
        if tag == 'script' and attrs.get('type') == 'application/ld+json':
            self.in_json = True
            self.json_parts = []
        if tag == 'link' and attrs.get('rel') == 'canonical':
            self.canonical.append(attrs.get('href'))
        if tag == 'meta' and attrs.get('name') == 'description':
            self.description.append(attrs.get('content', ''))
        if tag == 'img' and 'alt' not in attrs:
            self.errors.append('image has no alt attribute')
        for attr in ('href', 'src'):
            if attrs.get(attr):
                self.links.append(attrs[attr])

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        if self.in_json:
            self.json_parts.append(data)

    def handle_endtag(self, tag):
        if tag == 'head':
            self.in_head = False
        if tag == 'title':
            self.in_title = False
        if tag == 'script' and self.in_json:
            try:
                json.loads(''.join(self.json_parts))
            except ValueError:
                self.errors.append('invalid JSON-LD')
            self.in_json = False


def route(path):
    name = path.relative_to(DIST).as_posix()
    if name == 'index.html':
        return '/'
    if name.endswith('/index.html'):
        return '/' + name[:-11]
    return '/' + name.removesuffix('.html')


def main():
    pages = {route(p): Page(p) for p in sorted(DIST.rglob('*.html'))}
    if not pages:
        sys.exit('No built pages; run bun run build first.')
    errors = []
    titles = Counter(p.title for p in pages.values())
    for url, page in pages.items():
        failures = list(page.errors)
        failures += [f'duplicate id #{k}' for k, n in Counter(page.ids).items() if n > 1]
        if page.h1 != 1:
            failures.append(f'expected one h1, found {page.h1}')
        if page.title_count != 1 or not page.title or titles[page.title] != 1:
            failures.append('missing or duplicate page title')
        if page.canonical != [SITE + url]:
            failures.append(f'canonical does not match route {url}')
        if len(page.description) != 1 or not page.description[0].strip():
            failures.append('missing or duplicate description')
        for link in set(page.links):
            parsed = urlsplit(urljoin(SITE + url, link))
            if parsed.scheme not in ('http', 'https') or parsed.netloc != urlsplit(SITE).netloc:
                continue
            target = unquote(parsed.path).rstrip('/') or '/'
            if target in pages:
                if parsed.fragment and unquote(parsed.fragment) not in pages[target].ids:
                    failures.append(f'broken fragment {link}')
            elif not (DIST / target.lstrip('/')).is_file():
                failures.append(f'missing local target {link}')
        errors.extend(f'{url}: {f}' for f in failures)
    if errors:
        print('\n'.join(errors), file=sys.stderr)
        sys.exit(f'{len(errors)} site integrity error(s) in {len(pages)} pages')
    print(f'Verified {len(pages)} pages: local routes, fragments, assets, unique titles/IDs, headings and metadata')

if __name__ == '__main__':
    main()
