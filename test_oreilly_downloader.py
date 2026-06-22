"""Unit tests for oreilly_downloader.

These tests need NO network and NO real aiohttp server. A minimal async fake
session/response is provided inline (no aioresponses dependency).
"""

import asyncio

import pytest

import oreilly_downloader
from oreilly_downloader import DownloadError, _get_json, to_xhtml


# --------------------------------------------------------------------------- #
# Fakes: minimal async session/response with async-context-manager support.
# --------------------------------------------------------------------------- #
class FakeResponse:
    def __init__(self, status=200, content_type='application/json',
                 json_data=None, text_data=''):
        self.status = status
        self.headers = {'Content-Type': content_type}
        self._json_data = json_data
        self._text_data = text_data

    @property
    def ok(self):
        return self.status < 400

    async def json(self):
        # Simulate aiohttp raising when the body is not actually JSON: a correct
        # implementation must never reach here for a non-JSON Content-Type.
        if 'application/json' not in self.headers.get('Content-Type', ''):
            raise ValueError('not json')
        return self._json_data

    async def text(self):
        return self._text_data

    async def read(self):
        return self._text_data.encode('utf-8')

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeSession:
    def __init__(self, response):
        self._response = response
        self.requested_urls = []

    def get(self, url, **kwargs):
        self.requested_urls.append(url)
        return self._response


def run(coro):
    return asyncio.run(coro)


# --------------------------------------------------------------------------- #
# to_xhtml
# --------------------------------------------------------------------------- #
def test_to_xhtml_strips_root_path():
    root = '/api/v2/epubs/urn:orm:book:123/files/'
    html = (
        f'<div><a href="{root}chapter1.html">c1</a>'
        f'<img src="{root}img/cover.png"/></div>'
    )
    out = to_xhtml(html, root).decode('utf-8')
    assert root not in out
    assert 'href="chapter1.html"' in out
    assert 'src="img/cover.png"' in out


def test_to_xhtml_makes_void_tags_well_formed_xml():
    # O'Reilly .xhtml chapters contain HTML-style <img> with no self-close, which
    # is invalid XML; to_xhtml must produce parseable XML (else readers reject it).
    import xml.dom.minidom as minidom
    root = '/api/v2/epubs/urn:orm:book:123/files/'
    html = f'<html><body><p>hi<br><img src="{root}images/x.png" width="5"></p></body></html>'
    out = to_xhtml(html, root)
    minidom.parseString(out)  # raises if not well-formed
    assert root.encode() not in out  # asset prefix stripped


def test_to_xhtml_handles_comment_nodes():
    # Regression: full chapters contain HTML comments; tree.iter() yields them
    # and their .get() returns None, which used to crash on .startswith().
    root = '/api/v2/epubs/urn:orm:book:123/files/'
    html = (
        f'<div><!-- a comment --><a href="{root}c1.html">c1</a>'
        f'<?php nope ?><p>text</p></div>'
    )
    out = to_xhtml(html, root).decode('utf-8')
    assert 'href="c1.html"' in out
    assert root not in out


def test_to_xhtml_wraps_fragment_and_sets_title_from_h1():
    out = to_xhtml('<div><h1>My Chapter</h1><p>body</p></div>', '/root/').decode('utf-8')
    assert '<html' in out
    assert '<title>My Chapter</title>' in out
    assert '<body' in out


def test_to_xhtml_full_doc_passes_through_without_double_wrap():
    doc = '<html><head><title>Doc</title></head><body><p>hi</p></body></html>'
    out = to_xhtml(doc, '/root/').decode('utf-8')
    # Only one <html> element -> no double-wrap.
    assert out.count('<html') == 1
    assert '<title>Doc</title>' in out


# --------------------------------------------------------------------------- #
# _get_json guards
# --------------------------------------------------------------------------- #
def test_get_json_raises_downloaderror_on_html_200():
    resp = FakeResponse(
        status=200,
        content_type='text/html; charset=utf-8',
        text_data='<html><body>challenge</body></html>',
    )
    session = FakeSession(resp)
    with pytest.raises(DownloadError) as ei:
        run(_get_json(session, 'http://example/x'))
    msg = str(ei.value)
    assert 'text/html' in msg
    assert 'challenge' in msg


def test_get_json_raises_auth_failed_on_403():
    resp = FakeResponse(status=403, content_type='application/json')
    session = FakeSession(resp)
    with pytest.raises(DownloadError) as ei:
        run(_get_json(session, 'http://example/x'))
    msg = str(ei.value).lower()
    assert 'auth' in msg
    assert '403' in msg


def test_get_json_returns_data_on_success():
    resp = FakeResponse(
        status=200,
        content_type='application/json',
        json_data={'results': [], 'next': None},
    )
    session = FakeSession(resp)
    data = run(_get_json(session, 'http://example/x'))
    assert data == {'results': [], 'next': None}
