#!/usr/bin/env python3
"""Best-effort email/password login for O'Reilly that mints an ``orm-jwt`` cookie.

This is a BEST-EFFORT path only. O'Reilly's login is fronted by Akamai bot
protection and the upstream safaribooks project has already disabled its
``--cred``/``--login`` flow. Password login frequently fails behind a
bot/recaptcha challenge with no usable error. When it fails, this script exits
non-zero and tells the user to use the supported SSO/cookie path (the ``sso``
wrapper) instead.

On success it extracts the ``orm-jwt`` cookie from the authenticated session
and hands off to ``oreilly_downloader.py --jwt <jwt> <book_id>``.
"""

import argparse
import sys

import requests

LOGIN_ENTRY_URL = "https://learning.oreilly.com/login/unified/?next=/home/"
LOGIN_URL = "https://www.oreilly.com/member/auth/login/"
API_ORIGIN_URL = "https://api.oreilly.com"

USE_SSO_MSG = (
    "Password login is unreliable behind Akamai bot protection and upstream has "
    "disabled it. Please use the supported SSO cookie path instead: pipe your "
    "browser cookie JSON into the `sso` wrapper (see README)."
)


def fail(message):
    """Print a clear error to stderr (pointing at the SSO path) and exit 1."""
    print("Login error: %s" % message, file=sys.stderr)
    print(USE_SSO_MSG, file=sys.stderr)
    sys.exit(1)


def parse_cred(cred):
    """Split ``email:password`` on the first colon (passwords may contain ':')."""
    sep = cred.find(":")
    if sep < 0:
        fail("--cred must be in the form email:password.")
    return cred[:sep], cred[sep + 1:]


def do_login(session, email, password):
    """Replay O'Reilly's login; return the JWT bundle dict or fail() out."""
    try:
        entry = session.get(LOGIN_ENTRY_URL, timeout=30)
    except requests.RequestException as exc:
        fail("unable to reach O'Reilly login page: %s" % exc)

    redirect_uri = API_ORIGIN_URL + "/home/"

    try:
        response = session.post(
            LOGIN_URL,
            json={
                "email": email,
                "password": password,
                "redirect_uri": redirect_uri,
            },
            allow_redirects=False,
            timeout=30,
        )
    except requests.RequestException as exc:
        fail("unable to perform auth login: %s" % exc)

    if response.status_code != 200:
        snippet = response.text[:200].replace("\n", " ")
        fail(
            "auth login returned HTTP %s (likely a bot/recaptcha challenge or bad "
            "credentials). First bytes: %r" % (response.status_code, snippet)
        )

    ctype = response.headers.get("Content-Type", "")
    if "application/json" not in ctype:
        snippet = response.text[:200].replace("\n", " ")
        fail(
            "expected a JSON login response but got %r (likely an Akamai/bot "
            "challenge page). First bytes: %r" % (ctype, snippet)
        )

    try:
        jwt_bundle = response.json()
    except ValueError as exc:
        fail("login response was not valid JSON: %s" % exc)

    # Follow the redirect so the auth cookies (incl. orm-jwt) get set on the session.
    follow_url = jwt_bundle.get("redirect_uri") if isinstance(jwt_bundle, dict) else None
    if follow_url:
        try:
            session.get(follow_url, timeout=30)
        except requests.RequestException as exc:
            fail("unable to follow login redirect: %s" % exc)

    return jwt_bundle


def extract_orm_jwt(session, jwt_bundle):
    """Pull the orm-jwt out of the session cookies (falling back to the bundle)."""
    jwt = session.cookies.get("orm-jwt")
    if not jwt and isinstance(jwt_bundle, dict):
        jwt = jwt_bundle.get("orm-jwt") or jwt_bundle.get("jwt")
    if not jwt:
        fail(
            "logged in but no orm-jwt cookie was issued (challenge or account "
            "without epubs access)."
        )
    return jwt


def main():
    parser = argparse.ArgumentParser(
        description="Best-effort email/password login that mints an orm-jwt and "
        "downloads a book. Prefer the SSO cookie path."
    )
    parser.add_argument(
        "--cred",
        required=True,
        metavar="EMAIL:PASSWORD",
        help="O'Reilly credentials as email:password.",
    )
    parser.add_argument("book_id", help="The O'Reilly book id, e.g. 9780321635754.")
    args = parser.parse_args()

    email, password = parse_cred(args.cred)

    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})

    jwt_bundle = do_login(session, email, password)
    jwt = extract_orm_jwt(session, jwt_bundle)

    import subprocess

    result = subprocess.run(
        [sys.executable, "oreilly_downloader.py", "--jwt", jwt, args.book_id]
    )
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
