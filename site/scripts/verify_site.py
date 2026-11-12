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
import xml.etree.ElementTree as ET

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
        self.meta = {}
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
        if tag == 'meta':
            self.meta[attrs.get('name', attrs.get('property'))] = attrs.get('content', '')
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
    descriptions = Counter(p.description[0] for p in pages.values() if p.description)
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
        elif descriptions[page.description[0]] != 1:
            failures.append('description shared with another page')
        if ('noindex' in page.meta.get('robots', '')) != (url == '/404'):
            failures.append('unexpected indexing directive')
        for key, expected in {
            'og:title': page.title, 'twitter:title': page.title,
            'og:description': page.description[0] if page.description else '',
            'twitter:description': page.description[0] if page.description else '',
            'og:url': SITE + url,
            'og:image': SITE + '/og.png', 'twitter:image': SITE + '/og.png',
            'twitter:card': 'summary_large_image',
        }.items():
            if page.meta.get(key) != expected:
                failures.append(f'{key} does not match page metadata')
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
    # Check the generated XML against the complete built route inventory, rather
    # than assuming the sitemap integration discovered every dynamic task page.
    ns = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
    try:
        index = ET.parse(DIST / 'sitemap-index.xml')
        sitemap_urls = [el.text for el in index.findall('s:sitemap/s:loc', ns)]
        if not sitemap_urls:
            errors.append('sitemap index has no child sitemaps')
        locations = []
        for sitemap_url in sitemap_urls:
            parsed = urlsplit(sitemap_url)
            if not sitemap_url.startswith(SITE + '/') or parsed.query or parsed.fragment:
                errors.append(f'invalid child sitemap URL: {sitemap_url}')
                continue
            child = ET.parse(DIST / parsed.path.lstrip('/'))
            locations.extend(el.text for el in child.findall('s:url/s:loc', ns))
        expected = {SITE + url for url, page in pages.items() if 'noindex' not in page.meta.get('robots', '')}
        actual = set(locations)
        errors.extend(f'sitemap missing page: {url}' for url in sorted(expected - actual))
        errors.extend(f'sitemap contains noncanonical or nonindexable URL: {url}' for url in sorted(actual - expected))
        if len(locations) != len(actual):
            errors.append('sitemap contains duplicate URLs')
        if f'Sitemap: {SITE}/sitemap-index.xml' not in (DIST / 'robots.txt').read_text():
            errors.append('robots.txt does not advertise the sitemap index')
    except (ET.ParseError, OSError) as exc:
        errors.append(f'sitemap or robots.txt is missing or invalid: {exc}')
    if errors:
        print('\n'.join(errors), file=sys.stderr)
        sys.exit(f'{len(errors)} site integrity error(s) in {len(pages)} pages')
    print(f'Verified {len(pages)} pages: local routes, fragments, assets, unique titles/descriptions/IDs, headings, social metadata and sitemap coverage')

if __name__ == '__main__':
    main()
