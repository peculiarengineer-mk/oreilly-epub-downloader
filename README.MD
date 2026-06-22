# O'Reilly Downloader

A CLI to download O'Reilly books as epub, packaged via docker.

> ⚠️ **Educational purpose only.** This project exists to study how a modern
> SPA-over-JSON-API + EPUB pipeline works. It only operates with credentials and a
> subscription you already hold, for content you have access to, and it does **not**
> defeat any access control or bot protection. Use it for learning. Bulk or automated
> downloading may violate O'Reilly's
> [Terms of Service](https://learning.oreilly.com/terms/) — you are solely responsible
> for how you use it.

It uses O'Reilly's **v2 `epubs/files` manifest API**
(`/api/v2/epubs/urn:orm:book:{id}/files/`), which returns a paginated list of the
publisher's own EPUB files and streams them straight into a `.epub`. This replaces
the older per-chapter scraping approach.

## Supported path: SSO / JWT (recommended)

The **SSO cookie path is the supported, first-class path**: you export your browser
cookie JSON and pipe it into the `sso` wrapper, which extracts the `orm-jwt` cookie
and downloads the book. See [SSO Login](#sso-login) below.

## Best-effort path: email/password `login` (may fail)

The email/password `login` path is **best-effort only and may fail**. O'Reilly's
login is fronted by Akamai bot protection (and upstream disabled its password flow),
so it frequently fails with a challenge page. When it does, it exits with a clear
message pointing you to the SSO path. **Prefer SSO/JWT.**

# Requisite

- Docker
- O'Reilly Subscription

# Username/password login (best-effort)

> This path is best-effort and may fail behind Akamai bot protection — prefer the
> [SSO Login](#sso-login) path. If it fails, use SSO instead.

For users who has accounts with `username` and `password`.

First, find a book in O'Reilly Learning. Here I picked the famous `Art of Computer Programming` by Knuth,
you can find it at [https://learning.oreilly.com/library/view/art-of-computer/9780321635754/](https://learning.oreilly.com/library/view/art-of-computer/9780321635754/).

Copy the ID of the book (in this case `9780321635754`).

Run the docker command:

```sh
(docker run peculiarengineer-mk/orly:latest login <book id> <email:password>) > "<name of your file>.epub"
```

| argument            | explanation                                                         | example                       |
| ------------------- | ------------------------------------------------------------------- | ----------------------------- |
| `book id`           | the ID of the book                                                  | `9780321635754`               |
| ` email:password`   | your login credentials, by concatenating the with the `:` delimiter | `kirin@gmail.com:kirin1234`   |
| `name of your file` | The name of the file you want to save to, it can be anything        | `Art of Computer Programming` |

The full command will look like:

```sh
(docker run peculiarengineer-mk/orly:latest login 9780321635754 kirin@gmail.com:kirin1234) > "Art of Computer Programming.epub"
```

> Note that it will take a long time to download. Output is only buffered every 4k bytes (so you might not see any console output for awhile)

# SSO Login

SSO Login is much more complex. In SSO Login, we will need to extract your request cookie and add it to a file.

### Extracting Request Cookie

This is done using `Firefox` Browser. Other browsers do not have `Copy All` feature in the network tab. (Need to manually copy each field and convert it to `json`)

1. Login as usual to [https://learning.oreilly.com/](https://learning.oreilly.com/)
2. Open the developer tools with `F12`
3. Access the profile page in the browser: [https://learning.oreilly.com/profile/](https://learning.oreilly.com/)
4. Enter the command in the console: 
`opy(JSON.stringify(document.cookie.split(';').map(c => c.split('=')).map(i => [i[0].trim(), i[1].trim()]).reduce((r, i) => {r[i[0]] = i[1]; return r;}, {})))`
5. Paste this into any file. For this demo, we will assume you paste it into `cookie.json`.

Here is an example of how a `cookie.json` looks like. You do not need every field, this is just to show the syntax:

```json
{
	"BrowserCookie": "a3207952-2f4b-4a07-86d5-58df735a14d0",
	"csrfsafari": "rCJPYf19rQuPjvgkRovuYEwttDJy3T2rEADPdOVqdjk0SamNjfXFB2t1DkC5OnLg
9PljJrzh4v9Ju4yKMf5YpOsM7V3Sf0RWEq809izBkfEpbBQo4lqMYrRuJFAuGiQD",
	"groot_sessionid": "abcdefdghijkjlmnopqrstuvwxyz123456",
	"logged_in": "y",
	"orm-jwt": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyLCJlaWRzIjp7ImV4YWN0dGFyZ2V0IjoiaGVyb25fcHJvZF8xMjMxMjMxMjMxMjMxIiwiaGVyb24iOiJhYWFhYWFhYS1hYWFhLWFhYWEtYWFhYS1jY2NjY2NjY2FhMjIifSwiZW52IjoiZGV2ZWxvcG1lbnQiLCJleHAiOjE1MTU1NjYxMTEsImluZGl2aWR1YWwiOmZhbHNlLCJwZXJtcyI6eyJhY2FkbSI6InYiLCJhcGlkYyI6InYiLCJhc2lnbiI6InYiLCJjbmZyYyI6InYiLCJjc3N0ZCI6InYiLCJlcHVicyI6InYiLCJscnB0aCI6InYiLCJvcmlvbCI6InYiLCJwbHlscyI6InYiLCJ1c2FnZSI6InYiLCJ1c3JwZiI6InYiLCJ2aWRlbyI6InYifX0.E8VGI1i-pvrKMoJA36dC6tnIgw-bPJmfjexrU07BlNs",
	"orm-rt": "5f18b2d1267a3c81513cb10510bd7206",
	"salesforce_id": "e15031a5d19279e201c1eabf057b173a",
	"sessionid": "abcdefdghijkjlmnopqrstuvwxyz123456"
}
```

Now, assuming this file is `cookie.json`, we can proceed to pick a book in O'Reilly Learning.

Here I picked the famous `Art of Computer Programming` by Knuth,
you can find it at [https://learning.oreilly.com/library/view/art-of-computer/9780321635754/](https://learning.oreilly.com/library/view/art-of-computer/9780321635754/).

Copy the ID of the book (in this case `9780321635754`).

We can now download the book with the command:

```sh
(cat <cookie json file> | docker run -i peculiarengineer-mk/orly:latest sso <book id>) > "<name of your file>.epub"
```

| argument            | explanation                                                  | example                       |
| ------------------- | ------------------------------------------------------------ | ----------------------------- |
| `book id`           | the ID of the book                                           | `9780321635754`               |
| ` cookie json file` | the `json` file containing your request cookie details       | `cookie.json`                 |
| `name of your file` | The name of the file you want to save to, it can be anything | `Art of Computer Programming` |

```sh
(cat cookie.json | docker run -i peculiarengineer-mk/orly:latest sso 9780321635754) > "Art of Computer Programming.epub"
```

> Note that it will take a long time to download. Output is only buffered every 4k bytes (so you might not see any console output for awhile)

# Manual validation (first real book)

The v2 manifest layout has a few assumptions that are not provable from the
reference code alone. Before trusting a build, download **one real book** and check:

1. **`content.opf` location** — it actually lives at `EPUB/content.opf`, matching the
   `rootfile` declared in the synthesized `META-INF/container.xml`.
2. **Content doc extension** — content documents are `.html` (not `.xhtml`/`.htm`).
3. **`full_path` is EPUB-relative** — prefixing `EPUB/` does not produce a doubled
   `EPUB/EPUB/...` path.
4. **Manifest completeness** — the manifest includes the nav/toc document plus all
   spine items.
5. **In-document link prefix** — `href`/`src` attributes inside the documents begin
   with the `/api/v2/.../files/` prefix that the downloader strips.

# Terms of Service

This tool only works with credentials and a subscription you already hold, for books
you have access to. It changes *which* O'Reilly endpoint is called; it does not defeat
any access control or bot protection. Bulk or automated downloading may violate
O'Reilly's [Terms of Service](https://learning.oreilly.com/terms/) — you are
responsible for complying with them.

# Authors
[peculiarengineer-mk](https://github.com/peculiarengineer-mk)

# Credits
This project began as a Docker wrapper by [kirinnee](https://github.com/kirinnee)
and draws on the v2 `epubs/files` approach from
[xi/oreilly-downloader](https://github.com/xi/oreilly-downloader) and the original
[lorenzodifuccia/safaribooks](https://github.com/lorenzodifuccia/safaribooks). It has
since been rewritten to use O'Reilly's v2 manifest API directly.

# Contributing
See [contributing](./CONTRIBUTING.MD) for information on developing, its easy!
