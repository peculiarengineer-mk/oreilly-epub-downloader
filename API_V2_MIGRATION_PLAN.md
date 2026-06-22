# Dev Plan — Migrate Downloader to O'Reilly API v2 (`epubs/files`)

> Goal: replace the failing **v1 `/api/v1/book/{id}/`** metadata path with the **v2
> `/api/v2/epubs/urn:orm:book:{id}/files/`** manifest approach (as used by
> `xi/oreilly-downloader`), which delivers the publisher's own EPUB files directly.
> Built by 2 worker agents + 1 QA review; QA must-fixes folded in (marked **✎ QA**).
>
> ⚠️ **Scope/ethics:** This changes *which endpoint* we call — it does **not** defeat
> Akamai/bot protection. It only works with credentials you already hold, for books you're
> subscribed to. Bulk/automated downloading may violate O'Reilly's
> [Terms of Service](https://learning.oreilly.com/terms/); users are responsible for compliance.

---

## 0. 🔴 Do this FIRST — live-secret footgun (QA finding #6)

`cookies.json` (created during testing) holds a **live `orm-jwt` + `orm-rt` refresh token**. It is **not yet committed**, but `.gitignore` has a **typo** — it lists `cookie.json` (singular), which does **not** match `cookies.json`. So it's *unignored and untracked* → one `git add .` from being published.

- **Fix `.gitignore`:** add `cookies.json` (keep/也 fix `cookie.json`).
- **Rotate:** the token was pasted into a chat transcript earlier — log out of O'Reilly / let it expire.
- This is independent of the migration and should be done immediately.

---

## 1. Why v2 (verified)

The v2 `/files/` manifest returns a **paginated JSON list** of every file in the book (`results[]` with `url` + `full_path`, paged via `next`). The downloader just streams those files into a zip with the EPUB layout. This makes most of safaribooks redundant:

| v1 endpoint safaribooks uses | Purpose | v2 status |
|------------------------------|---------|-----------|
| `/api/v1/book/{id}/` (**the one that crashed**) | metadata for `content.opf` | ✅ not needed — `content.opf` is a file in the manifest |
| `/api/v1/book/{id}/chapter/?page=N` | chapter crawl | ✅ not needed — manifest lists all HTML |
| per-chapter HTML scrape | extract `#sbo-rt-content` | ✅ not needed — download file directly |
| `/api/v1/book/{id}/toc/` | build `toc.ncx` | ✅ not needed — nav doc is in manifest |
| image/CSS asset fetch | binary assets | ✅ not needed — assets are manifest entries |
| `mimetype`, `META-INF/container.xml` | EPUB wrappers | ⚠️ still synthesized client-side (2 static files) |

**Auth:** single `orm-jwt` cookie on every request; optional liveness check via
`GET /api/v1/user-preferences/` (returns ok/not-ok, non-fatal).

---

## 2. Approach — VENDOR a small v2 downloader (recommended)

Add a ~120-line `oreilly_downloader.py` to the repo (modeled on xi's) and have `login`/`sso` call it. Rejected alternative: fork safaribooks + patch — it leaves ~1100 lines of now-dead scraping code to maintain.

**Bonus:** vendoring lets us delete the unpinned `git clone` (Dockerfile:3) — directly resolving the supply-chain finding **G** from the earlier review.

**✎ QA #3:** the script does not exist in the repo yet — it must be added **before** the Dockerfile drops the clone.

---

## 3. The downloader module (`oreilly_downloader.py`)

Reuse xi's structure, but **harden the JSON parsing** — this is the actual bug you hit.

- `to_xhtml(s, root_path)` — unchanged: lxml parse, strip `root_path` from `href`/`src`, wrap fragments in `<html>` with epub nsmap.
- `check_auth(session)` — `GET /api/v1/user-preferences/`, return `r.ok` (advisory).
- **`_get_json(session, url)` — NEW, the centerpiece (✎ QA #1 must-fix):** xi does a bare
  `await r.json()` (`oreilly_downloader.py:82-83`) with no guard, so a **200 + HTML**
  Akamai/SSO bounce throws an unhandled `JSONDecodeError`/`ContentTypeError` — exactly your
  crash. Guard order = **status first, then Content-Type**:
  ```python
  async def _get_json(session, url):
      async with session.get(url, raise_for_status=False) as r:
          if r.status in (401, 403):
              raise DownloadError(f'Auth failed ({r.status}): orm-jwt missing/expired/no epubs access.')
          if r.status >= 400:
              raise DownloadError(f'HTTP {r.status} fetching {url}.')
          if 'application/json' not in r.headers.get('Content-Type', ''):
              snippet = (await r.text())[:200].replace('\n', ' ')
              raise DownloadError(f'Expected JSON, got {r.headers.get("Content-Type")!r} '
                                  f'(status {r.status}) — likely a bot/challenge or expired session. '
                                  f'First bytes: {snippet!r}')
          return await r.json()
  ```
- `fetch_book(book_id, zfh, session)` — write `mimetype` (ZIP_STORED, first) + `container.xml`;
  loop `while url:` calling `_get_json`, download each `results[]` entry into
  `EPUB/{full_path}`, follow `next`. **✎** add `asyncio.Semaphore(8)` to bound concurrency
  (xi's unbounded `gather` opens hundreds of connections → 429/FD exhaustion on big books),
  and skip entries missing `url`/`full_path` with a stderr warning.
- `amain()` — `try/except DownloadError → print to stderr, sys.exit(1)` (no traceback; lets the
  wrapper's `set -e` abort cleanly before the "please star" echo).

---

## 4. Output & CLI contract (✎ QA #7)

Write `{book_id}.epub` **to disk**, wrapper `cat`s it — do **not** stream the zip to stdout
(`ZipFile` seeks back on close to write the central directory; stdout isn't seekable).

- **All tool logs/progress → stderr** (stdout is reserved for epub bytes only).
- **✎ QA #7 caveat:** update the wrappers' `cat "$(find . -name "$1".epub)"` to `cat "$1.epub"`
  since the new tool names the file `<id>.epub` (the old `find` would match nothing and `set -eu`
  would abort). Side benefit: removes the fragile `find/cat` (review finding **C**).

**`sso <book_id>`** (primary, supported):
```sh
set -eu
cat - > cookies.json
JWT=$(python3 -c 'import json;print(json.load(open("cookies.json"))["orm-jwt"])')
python3 oreilly_downloader.py --jwt "$JWT" "$1" 1>&2
cat "$1.epub"
```

**`login <book_id> <email:password>`** (secondary, best-effort — see risk):
```sh
set -eu
python3 oreilly_login.py --cred "$2" "$1" 1>&2   # mints orm-jwt, then downloads
cat "$1.epub"
```

---

## 5. Auth wiring & the `login` risk (✎ QA #5)

- **sso path:** `orm-jwt` is a top-level key in the piped cookie JSON → extract and pass. Clean.
- **login path:** v2 needs an `orm-jwt`, which email+password doesn't directly give. You'd
  replay O'Reilly's login (POST `/member/auth/login/`, response carries the JWT bundle, follow
  `redirect_uri` to set cookies) — the blueprint is safaribooks `do_login` (`safaribooks.py:464-516`).
  **✎ QA #5 — critical:** upstream safaribooks has **already disabled** `--cred`/`--login`
  (`safaribooks.py:1097-1102` prints a warning and exits; body commented out). So **your current
  `login` script is already dead** — only `sso` works today. Behind Akamai, password login is
  unreliable. **Recommendation: make SSO/JWT the only first-class path**; either reimplement
  `login` as explicitly best-effort (failing with a clear DownloadError pointing to the SSO path)
  or deprecate it in the README.

---

## 6. Dockerfile (✎ QA #8)

Replace the clone with the vendored script; drop git; keep non-root `appuser`.
```dockerfile
FROM python:3
RUN pip3 install --no-cache-dir aiohttp lxml
WORKDIR /app
COPY oreilly_downloader.py oreilly_login.py sso login ./
RUN chmod 0755 sso login && mv sso login /usr/bin/
RUN useradd -m appuser && chown -R appuser /app
USER appuser
```
- **✎ QA #8:** keep base `python:3` (full Debian) — lxml/aiohttp install from self-contained
  manylinux wheels, no system libs needed. **If** you switch to `python:3-slim`, pin lxml to a
  wheel-available version or add `libxml2-dev libxslt-dev gcc` as a build fallback.
- `chmod 0755` (not `o+x`) — these are app files we own; avoids the H/I `o+x` coupling.
- `USER appuser` stays **last**; `chown -R appuser /app` so the epub is writable.
- `requests` dependency drops out.

---

## 7. Test plan (✎ QA — no real creds needed)

**Unit (pytest, mocked):**
1. `to_xhtml` strips `root_path` from href/src.
2. `to_xhtml` wraps a bare fragment in `<html>` + derives `<title>` from `<h1>`.
3. `to_xhtml` passes a full `<html>` doc through without double-wrapping.
4. Pagination: mock page1→`next`→page2→`next:null`; assert both pages' results downloaded, `mimetype` ZIP_STORED + `container.xml` present.
5. Malformed entry (missing `full_path`/`url`) skipped with warning, no crash.
6. **Guard — non-JSON body:** mock `200 + text/html` → raises `DownloadError` (not JSONDecodeError), message names Content-Type + snippet.
7. **Guard — 401/403:** status branch fires before Content-Type; message says "auth failed".

**Integration smoke (no creds):**
8. `python3 oreilly_downloader.py --help` exits 0.
9. `docker run --rm <img> whoami` → `appuser`.
10. Bogus `--jwt` → exit 1, one-line stderr error, **no traceback**, "please star" echo absent (verifies `set -e` ordering).

---

## 8. Unproven assumptions — validate against ONE real book before declaring done (✎ QA)

These are **not** provable from the reference code; verify on a first real download:
1. **`content.opf` lives at `EPUB/content.opf`** — the hardcoded `container.xml` rootfile must
   equal the opf's actual `full_path`, or the EPUB won't open.
2. **Content docs are `.html`** (so `to_xhtml` fires) vs `.xhtml`/`.htm`.
3. **`full_path` is EPUB-relative** (prefixing `EPUB/` doesn't double up).
4. **The manifest actually contains the nav/NCX + all spine items** as `results`.
5. **In-document href/src** begin with the `/api/v2/.../files/` prefix `to_xhtml` strips.

---

## 9. Task checklist

- [ ] **0.** Fix `.gitignore` (`cookies.json`), rotate token. *(do now)*
- [ ] **1.** Vendor `oreilly_downloader.py` with the `_get_json` guard + semaphore.
- [ ] **2.** Decide login: reimplement `oreilly_login.py` (best-effort) **or** deprecate `login`.
- [ ] **3.** Update `sso`/`login` wrappers (JWT extract, `cat "$1.epub"`, keep `set -eu`).
- [ ] **4.** Rewrite Dockerfile (drop clone/git, add deps, keep appuser) — closes finding **G**.
- [ ] **5.** Add pytest unit tests + Docker smoke tests (§7).
- [ ] **6.** Validate the 5 assumptions (§8) against one real book; fix `container.xml` path if needed.
- [ ] **7.** Update README: SSO/JWT is the supported path; ToS note.

---

## QA verdict

> "The plan's core technical claims are sound — v2 single-cookie auth, manifest pagination, the
> write-to-disk rationale, the JSON-guard robustness gap, the disabled upstream `--cred` path, and
> the dependency/Docker simplification all check out against the actual code." Implementable once
> the 5 must-fixes (guard, `.gitignore`, vendor-before-clone-removal, output glob, validate
> assumptions) are folded in — **all incorporated above.**
