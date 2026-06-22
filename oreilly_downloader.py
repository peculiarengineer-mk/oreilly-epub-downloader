# /// script
# dependencies = [
#   "aiohttp",
#   "lxml",
# ]
# ///

"""Vendored O'Reilly v2 EPUB downloader.

Downloads a book's EPUB by streaming the publisher's own files listed in the
v2 manifest (``/api/v2/epubs/urn:orm:book:{id}/files/``) into a zip with the
EPUB layout.

IMPORTANT: stdout is reserved for EPUB bytes by the ``sso``/``login`` wrappers.
Every progress / log / warning message MUST go to ``sys.stderr``.
"""

import argparse
import asyncio
import sys
import zipfile

import aiohttp
from lxml import etree
from lxml import html as lhtml

BASE_URL = 'https://learning.oreilly.com'

def container_xml(opf_path):
    """Build META-INF/container.xml pointing at the real package document.

    The package document is not always EPUB/content.opf — different books ship
    it as package.opf, etc. Hardcoding the path makes readers unable to find the
    package and refuse to open the book, so we detect it from the manifest.
    """
    container = (
        '<?xml version="1.0"?>\n'
        '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" '
        'version="1.0">\n'
        '    <rootfiles>\n'
        '        <rootfile full-path="%s" '
        'media-type="application/oebps-package+xml"/>\n'
        '    </rootfiles>\n'
        '</container>\n'
    ) % opf_path
    return container.encode('utf-8')


class DownloadError(Exception):
    """Raised for any recoverable, user-facing download failure.

    Caught in ``amain`` to print a clean one-line error to stderr and exit 1
    (no traceback), so the wrapper's ``set -e`` aborts cleanly.
    """


def to_xhtml(s, root_path):
    tree = lhtml.fromstring(s, parser=lhtml.HTMLParser(encoding='utf-8'))

    for el in list(tree.iter()):
        # tree.iter() also yields comment / processing-instruction nodes, whose
        # .get() returns None (ignoring the default) and which have no attributes
        # to set. Skip anything that isn't a real element tag.
        if not isinstance(el.tag, str):
            continue
        for attr in ['href', 'src']:
            val = el.get(attr)
            if val and val.startswith(root_path):
                el.set(attr, val.removeprefix(root_path))

    if tree.tag != 'html':
        wrapper = etree.Element('html', nsmap={
            None: 'http://www.w3.org/1999/xhtml',
            'epub': 'http://www.idpf.org/2007/ops',
        })

        h1 = tree.find('.//h1')
        if h1 is not None:
            head = etree.SubElement(wrapper, 'head')
            title = etree.SubElement(head, 'title')
            title.text = ''.join(h1.itertext()).strip()

        body = etree.SubElement(wrapper, 'body')
        body.append(tree)
        tree = wrapper

    return etree.tostring(
        tree,
        xml_declaration=True,
        doctype='<!DOCTYPE html>',
        pretty_print=True,
        encoding='utf-8',
    )


async def check_auth(session):
    """Advisory liveness check. Returns True if the session looks authorized."""
    url = BASE_URL + '/api/v1/user-preferences/'
    async with session.get(url, raise_for_status=False) as r:
        return r.ok


async def _get_json(session, url):
    """GET ``url`` and return parsed JSON, guarding against non-JSON bounces.

    A 200 + HTML response (Akamai/SSO challenge) would otherwise blow up with an
    unhandled JSONDecodeError/ContentTypeError. Guard order is **status first,
    then Content-Type**.
    """
    async with session.get(url, raise_for_status=False) as r:
        if r.status in (401, 403):
            raise DownloadError(
                f'Authentication failed ({r.status}): '
                f'orm-jwt missing/expired or no epubs access.'
            )
        if r.status >= 400:
            raise DownloadError(f'HTTP {r.status} fetching {url}.')
        if 'application/json' not in r.headers.get('Content-Type', ''):
            snippet = (await r.text())[:200].replace('\n', ' ')
            raise DownloadError(
                f'Expected JSON, got {r.headers.get("Content-Type")!r} '
                f'(status {r.status}) - likely a bot/challenge page or '
                f'expired session. First bytes: {snippet!r}'
            )
        return await r.json()


async def fetch_book(book_id, zfh, session):
    root_path = f'/api/v2/epubs/urn:orm:book:{book_id}/files/'

    sem = asyncio.Semaphore(8)

    async def download(url, path):
        async with sem:
            async with session.get(url) as r:
                content = await r.read()
        # O'Reilly serves chapters as .xhtml containing HTML-style void tags
        # (<img>, <br> with no self-close), which are invalid XML and make strict
        # EPUB readers reject the book. Normalise every (x)html file through
        # to_xhtml() so it is well-formed XML and the /api/v2/... asset prefixes
        # are stripped to relative paths.
        if path.endswith(('.html', '.xhtml', '.htm')):
            content = to_xhtml(content, root_path)
        zfh.writestr(path, content)

    # EPUB wrappers: mimetype MUST be first and stored (uncompressed).
    zfh.writestr('mimetype', b'application/epub+zip', compress_type=zipfile.ZIP_STORED)

    opf_path = None
    url = BASE_URL + root_path
    while url:
        print(f'fetching {url}', file=sys.stderr)
        data = await _get_json(session, url)

        tasks = []
        for result in data.get('results', []):
            file_url = result.get('url')
            full_path = result.get('full_path')
            if not file_url or not full_path:
                print(
                    f'warning: skipping manifest entry missing url/full_path: '
                    f'{result!r}',
                    file=sys.stderr,
                )
                continue
            dest = f'EPUB/{full_path}'
            # Remember the package document so container.xml can point at it.
            if opf_path is None and (
                result.get('media_type') == 'application/oebps-package+xml'
                or full_path.endswith('.opf')
            ):
                opf_path = dest
            tasks.append(download(file_url, dest))

        await asyncio.gather(*tasks)

        url = data.get('next')

    # Written after the manifest so it references the actual package document
    # path (content.opf, package.opf, ...). mimetype stays the first entry.
    zfh.writestr('META-INF/container.xml', container_xml(opf_path or 'EPUB/content.opf'))


async def amain():
    parser = argparse.ArgumentParser()
    parser.add_argument('book_id')
    parser.add_argument('--jwt')
    args = parser.parse_args()

    filename = f'{args.book_id}.epub'

    try:
        with zipfile.ZipFile(filename, 'w') as zfh:
            async with aiohttp.ClientSession(
                cookies={'orm-jwt': args.jwt} if args.jwt else {},
            ) as session:
                if not args.jwt:
                    print('No JWT provided. Continuing without...', file=sys.stderr)
                elif await check_auth(session):
                    print('Authentication successful.', file=sys.stderr)
                else:
                    print('Authentication failed. Continuing without...', file=sys.stderr)

                await fetch_book(args.book_id, zfh, session)
    except DownloadError as e:
        print(f'error: {e}', file=sys.stderr)
        sys.exit(1)

    print(f'created {filename}', file=sys.stderr)


if __name__ == '__main__':
    asyncio.run(amain())
