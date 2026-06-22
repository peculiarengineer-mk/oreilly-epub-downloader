# Dev Plan — Medium-Priority Review Fixes (B, I, J, L, M)

> Scope: the five **medium**-priority findings only. High-priority items (C `find/cat`,
> H `chmod o+x`, etc.) are explicitly **out of scope** but called out where they couple.
> Plan reviewed by a QA sub-agent; corrections incorporated (see notes marked **✎**).

## Summary

| # | File | Change | Risk |
|---|------|--------|------|
| B | `login`, `sso` | Add `set -eu`; abort before the "please star" message on failure | Low |
| I | `Dockerfile` | Add non-root `appuser`, `chown` workdir, `USER appuser` last | Medium |
| J | `.github/workflows/build.yaml` | Add least-privilege `permissions:` block | Low |
| L | `.github/workflows/build.yaml` | `ubuntu-latest`, `checkout@v4`, `docker.pkg.github.com` → `ghcr.io` | Medium |
| M | `pls.nix`, `packages.nix` | Drop unused binding, quote `"$@"`, expose `pl0x` | Low |

---

## Item B — Strict mode in shell scripts

**Files:** `login:1-2`, `sso:1-2`

1. Insert `set -eu` as line 2 (after the `#!/bin/sh` shebang) in **both** scripts.
2. With `set -e`, a non-zero exit from `python3 safaribooks.py …` (or the `cat`) aborts the
   script **before** the "Please ⭐ …" echo, so the message no longer prints on failure.
3. `set -u` makes a missing `$1`/`$2` fail fast with a clear error instead of running
   `safaribooks.py` with empty args.

**Out of scope:** the `cat "$(find …)"` fragility is high-priority item **C** — leave it.
✎ Note: under `set -e`, an empty `find` result still causes the `cat` to fail and abort
before the echo, which is the desired behavior here.

**Verify:** `shellcheck login sso` (the pre-existing `echo "\t…"` portability warning is
unrelated/out of scope), and a manual run where `safaribooks.py` exits non-zero must **not**
print the star message.

---

## Item I — Non-root container user

**File:** `Dockerfile` (append after the existing `chmod/mv` RUN on line 8)

1. Create a non-root user and give it ownership of the runtime workdir:
   ```dockerfile
   RUN useradd -m appuser && chown -R appuser /safaribooks
   USER appuser
   ```
2. `chown -R appuser /safaribooks` is **required** — the dir is created root-owned by
   `git clone`, and `cookies.json` + the `Books/` output are written there at runtime.
3. **Ordering (✎ enforced):** `USER appuser` must be the **last** instruction — after all
   root-requiring steps (apt, git clone, pip install, COPY, chmod, mv) and after the `chown`.

**Coupling with high-priority item H (✎ important):** the scripts in `/usr/bin` are
root-owned and currently `chmod o+x`. `appuser` is in the *other* class for those files, so
**`o+x` is exactly what lets the non-root user exec them** — it is load-bearing here.
Do **not** touch `chmod o+x` in this change. When H is eventually addressed, it must keep an
execute bit reachable by `appuser` (e.g. `chmod 0755`), or non-root exec breaks.

**Verify:** `docker build .` succeeds; `docker run --rm <img> sh -c 'whoami'` → `appuser`;
a real `login`/`sso` run can write `cookies.json` and the epub output.

---

## Item J — CI least-privilege permissions

**File:** `.github/workflows/build.yaml` (top level, after the `on:` block)

1. Add:
   ```yaml
   permissions:
     contents: read
     packages: write
   ```
2. ✎ An explicit `permissions:` block drops every unlisted scope to `none`. This workflow
   only checks out code and pushes images, so these two scopes are sufficient.
3. `packages: write` is what authorizes the `GITHUB_TOKEN` GHCR push from item L — keep J and
   L together.

**Verify:** YAML lint; the GHCR push step authenticates with `GITHUB_TOKEN`.

---

## Item L — CI modernization

**File:** `.github/workflows/build.yaml`

1. `runs-on: ubuntu-20.04` → `runs-on: ubuntu-latest` (line 11).
2. `actions/checkout@v2` → `actions/checkout@v4` (line 20).
3. Migrate off the shut-down GitHub Packages Docker registry to GHCR:
   - **Login (line 23):**
     ```yaml
     run: echo "${{ secrets.GITHUB_TOKEN }}" | docker login ghcr.io -u ${{ github.actor }} --password-stdin
     ```
   - **Image ref (lines 27-28):** ✎ **Correction** — use `github.repository_owner`, **not**
     `github.repository` (which is already `owner/repo` and would produce a 3-segment path).
     Keep the existing lowercase normalization (GHCR requires lowercase):
     ```bash
     IMAGE_ID=ghcr.io/${{ github.repository_owner }}/$CI_DOCKER_IMAGE
     IMAGE_ID=$(echo $IMAGE_ID | tr '[A-Z]' '[a-z]')
     ```
     → resolves to `ghcr.io/peculiarengineer-mk/orly`.
4. Leave the DockerHub login/push steps unchanged.

**Verify:** workflow YAML lint; on a test push to `main`, confirm the image lands at
`ghcr.io/peculiarengineer-mk/orly:latest` and the DockerHub push still succeeds.

---

## Item M — Nix cleanup

**Files:** `pls.nix`, `packages.nix`

1. `pls.nix:4` — remove the unused `let task = go-task; in` binding (`task` is never
   referenced; wrappers use `${go-task}` directly).
2. `pls.nix:8,11,14,17` — quote the argument forwarding: `${go-task}/bin/go-task "$@"`.
   ✎ Inside Nix `''…''` strings the double quotes are literal — no Nix-level escaping needed.
3. Resolve the `pl0x` dead code by **exposing** it (keeps the alias). In `packages.nix:6-10`,
   add `pl0x` to the list:
   ```nix
   [ pls please plz pl0x ]
   ```
   (`pls.nix` already defines/exports `pl0x`, so this is a one-line addition with no eval risk.)

**Verify:** `nix-shell` evaluates `shell.nix`/`packages.nix` without error; `pls`, `please`,
`plz`, and `pl0x` are all on `PATH` and forward args correctly (e.g. `pls --list`).

---

## Suggested commit grouping

1. `fix(scripts): add set -eu so failures don't print success message` — item B
2. `fix(docker): run container as non-root appuser` — item I
3. `ci: add least-privilege permissions and migrate to ghcr.io` — items J + L (kept together)
4. `chore(nix): drop unused binding, quote "$@", expose pl0x` — item M

## Global validation

- `docker build .` (covers B-script COPY + I).
- `shellcheck login sso`.
- `nix-shell --run 'pls --version'`.
- YAML review of `build.yaml`; a branch push to confirm GHCR + DockerHub pushes.

## QA review outcome

A review sub-agent verified each item against the live files. Verdict: plan sound; **one
correction** (GHCR ref → `github.repository_owner`) and clarifications on the H/I `o+x`
coupling and `USER` ordering — all folded in above. No step breaks the build as corrected.
