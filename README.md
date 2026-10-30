# mcp-ultimate

A single, lightweight Dockerized MCP server exposing a growing set of free,
mostly keyless "skills" over both SSE and Streamable HTTP. Built to run on a
home LAN box and be pointed at by any MCP-speaking agent.

- **Transport:** both served from the same process/port --
  SSE at `http://<host>:8088/sse`, Streamable HTTP at `http://<host>:8088/mcp`.
  Same server instance, same tools, either works -- use whichever your client
  supports or prefers (Streamable HTTP is the current MCP spec's recommended
  transport; SSE is kept for clients that still expect it).
- **Image:** Python 3.12-slim + headless-shell Chromium (Playwright) + git + ruff, ~1.54GB
- **Extending it:** drop a new file in `skills/` with a `register(mcp)`
  function -- `server.py` auto-discovers it on the next container restart, no
  other wiring required. See [Adding a new skill](#adding-a-new-skill).

## How it works

```
server.py            FastMCP app. Walks skills/, imports every module,
                      calls module.register(mcp) if present.
skills/config.py      Shared env-driven settings (timeouts, limits) that
                      more than one skill file imports.
skills/*.py           One file per skill. Each defines its tool function(s)
                      at module level (so other skills can import and reuse
                      them -- see itinerary.py) plus a register(mcp) that
                      wires them up as MCP tools.
```

The container runs as a non-root user with no host filesystem mounts --
`sandbox`'s shell/file tools are contained to the image and a single named
Docker volume (`mcp_workspace`), not your host disk.

## Skill catalog (49 tools)

Any skill can be turned off without touching code -- see
[Enable/disable skills](#enabledisable-skills).

### Search & information
| Tool | What it does | Source | Key needed? |
|---|---|---|---|
| `web_search(query, max_results)` | General web search | Bing (scraped) first, your SearXNG instance as fallback | No |
| `search_news(query, max_results)` | News search, 1-sentence summary per result | Bing News (scraped) first, your SearXNG instance as fallback | No |
| `fetch_url(url, max_chars)` | Read a specific page's text (no JS) | httpx + selectolax | No |
| `browse(url, max_chars, scroll_to_bottom)` | Read a specific page's text, JS rendered | Headless Chromium (Playwright) | No |
| `get_weather(location)` | Current conditions + forecast, city name or US zip | Open-Meteo + Zippopotam.us | No |
| `get_time(timezone)` | Current time in an IANA timezone | stdlib `zoneinfo` | No |
| `convert_currency(amount, from, to)` | FX conversion | Frankfurter (ECB rates) | No |
| `get_crypto_price(coin_id, vs_currency)` | Crypto spot price | CoinGecko | No |

**`web_search`/`search_news`'s fallback chain** (`skills/search_engines.py`): each
tries Bing/Bing News first, SearXNG second, by default -- controlled by
`SEARCH_PREFER_BROWSER` (`true`/`false`). Within the Bing attempt itself
there's a second, nested fallback: a plain HTTP request first (fast, ~0.2-1s,
no browser needed since Bing's results are server-rendered), and only if that
returns nothing parseable, a headless-Chromium render as a second try before
giving up on Bing and moving to SearXNG. So a single `web_search` call can
involve up to three attempts: Bing-via-HTTP, Bing-via-browser, SearXNG.
Flip `SEARCH_PREFER_BROWSER=false` to put SearXNG first instead (faster -- no
possibility of a slow browser-render step -- and self-hosted/under your
control, with Bing as the fallback if SearXNG is down). Both orderings use
the same `random_headers()` as `fetch_url`/`browse`. Like `search_flights`,
this scrapes a page Bing doesn't officially offer a free API for and could
break if they change their markup -- the CSS selectors
(`li.b_algo`, `.news-card`) are hardcoded against today's layout.

### Travel
| Tool | What it does | Notes |
|---|---|---|
| `search_flights(from_airport, to_airport, departure_date, return_date, ...)` | Real, current flight prices/schedules from Google Flights, ranked by price, plus Expedia/Skyscanner/Priceline comparison links | See "Travel sites: what's real vs. a link" below |
| `search_hotels(destination, check_in, check_out, ...)` | Real Google Hotels prices/ratings/amenities, plus Booking.com/Kayak/Expedia/Priceline/Skyscanner comparison links | See below |
| `search_car_rentals(location, pickup_date, dropoff_date)` | Kayak (confirmed) + Expedia (best-effort) + Priceline/Skyscanner (plain landing pages) + Google fallback | See below |
| `search_packages(origin_airport, destination, check_in, check_out, adults)` | Expedia (confirmed official format) + Priceline (plain landing page) flight+hotel package links | Google Travel and Skyscanner don't have a packages product |
| `search_flights_kayak(from_airport, to_airport, departure_date, max_results)` | Real Kayak flight prices/airlines/times, as a cross-check against `search_flights`'s Google Flights data | One-way only. Slower (~5-20s vs under a second) -- see below |
| `search_hotels_kayak(destination, check_in, check_out, max_results)` | Real Kayak hotel prices/ratings, as a cross-check against `search_hotels`'s Google Hotels data | Same latency caveat as above |
| `plan_trip(origin_airport, destination_airport, destination_city, departure_date, return_date, ...)` | One combined itinerary: flights + weather + attractions | Composes `search_flights` + `get_weather` + `web_search` -- no new data source |

#### Travel sites: what's real vs. a link

Researched and tested live against Expedia, Priceline, Skyscanner, and Google
Travel across flights/hotels/packages before building anything (see git
history for the full investigation). Results varied sharply by site:

- **Google Flights & Google Hotels: real scraped data.** Flights via
  `fast-flights`; hotels via `fast-hotels` (same undocumented-internal-API
  approach, same author ecosystem). Both scrape pages Google doesn't offer a
  free API for -- could break if Google changes their markup, same ToS
  caveat as before. `fast-hotels` also shipped with a hardcoded, outdated
  `primp` browser-impersonation string (`chrome_126`) that current `primp`
  releases reject outright -- `skills/hotels.py` monkeypatches
  `fast_hotels.core.Client` at import time to fix it (patching `primp.Client`
  itself doesn't work: it's a compiled PyO3 extension type whose `__init__`
  can be silently reassigned but is never actually called during
  construction). Also worth knowing: live Google Hotels responses are
  frequently (observed ~1 in 3 calls, not rare) a degraded variant
  `fast-hotels` parses into near-empty records (`rating=None`, implausible
  `$0.0`/`$1.0` prices) instead of raising -- `search_hotels` detects this
  (`_looks_degraded`) and retries up to 3 times before falling back to a
  clear message; stress-tested 5 consecutive calls after adding the retry,
  all 5 came back complete.
- **Kayak: real scraped data too, for both flights and hotels** (separate
  tools, `search_flights_kayak`/`search_hotels_kayak`, not merged into the
  Google-backed defaults -- see below for why). Unlike Bing, Kayak's results
  are 100% client-side rendered (confirmed: a plain HTTP GET returns zero
  result markup) and stream in progressively over several seconds rather
  than being present at load, so these poll for the result selector instead
  of a fixed sleep or `networkidle` (which Kayak may never actually reach).
  Two real bugs found while building this, both now fixed:
  - The *already-shipped* Kayak deep links in `search_hotels`/
    `search_car_rentals` were broken: a comma in the destination slug
    (`Austin,-TX`) silently redirects hotels to Kayak's generic `/stays`
    landing page instead of real results, and for cars it's worse -- it
    silently resolves to the **wrong city** (`Los-Angeles,-CA` landed on
    Carlsbad, not LA). Confirmed by checking the actual post-redirect URL
    and page title, not just HTTP status (200 in both the broken and fixed
    cases). Fixed by stripping commas before hyphen-joining.
  - Setting `extra_http_headers` (the Accept/Accept-Language/Accept-Encoding/
    etc bundle `fetch_url`/`browse` use) made Kayak's **flights** vertical
    return zero results, even though the main HTML page still loaded fine
    (200, correct title) -- something in that header set breaks Kayak's
    background result-streaming calls specifically. Fixed by using a plain
    `User-Agent` alone for Kayak, no extra headers.
  Kayak's CSS classes are algorithmically-generated hashes (`.nrc6-wrapper`,
  `.e2GB-price-text`, `.S0Ps-resultInner`), not semantic names like Bing's
  `.b_algo` -- meaningfully more likely to break on any Kayak frontend
  deploy than the other scrapers here. `search_flights_kayak`'s "airline"
  field sometimes shows the booking agency Kayak routes through (e.g.
  "Priceline") rather than the operating carrier -- that's Kayak's own
  display choice as a metasearch site, not a parsing bug.
- **TripAdvisor: blocked.** Tested live -- HTTP 403 with a CAPTCHA marker on
  a basic hotel listing page, same pattern as Expedia/Priceline just from a
  different vendor. Not pursued further for the same reason as those two.
- **Expedia and Priceline: blocked outright.** Both run PerimeterX, an
  enterprise bot-management product -- confirmed live with HTTP 429 titled
  "Bot or Not?" (Expedia) and HTTP 403 "px-captcha" (Priceline), on every
  vertical tested (flights, hotels, packages). This is a CAPTCHA/enterprise
  bot-detection wall, not basic detection -- getting past it means solving
  CAPTCHAs, which this project won't do regardless of target (same call as
  dropping the DuckDuckGo-backed `browser_search` earlier, just a much
  bigger vendor). Expedia's hosted `expedia.com/mcp` connector also 403'd
  even with realistic headers -- likely gated behind ChatGPT/Claude's own
  connector registration, not a plain endpoint this server can bridge to.
- **Skyscanner: blocked for live prices.** Confirmed by Skyscanner MCP
  projects' own authors: one states outright that live fares "sit behind
  Skyscanner's anti-bot protection," another ships affiliate deep-links
  instead of real scraping.
- **Deep links for the blocked sites and verticals are a mix of confirmed
  and best-effort.** Expedia hotels/flights/packages and Kayak hotels/cars
  use documented or tested-working URL formats -- tested by checking the
  actual post-redirect URL and page title/content, not just HTTP status,
  after the Kayak comma bug above showed that 200 alone doesn't mean a link
  landed where intended. Several others (Priceline
  across the board, Skyscanner hotels/cars) have no confirmed parameterized
  format -- guessed query strings either 404'd or couldn't be verified at
  all (Priceline 403s even a bare page load from this environment, likely
  datacenter-IP-based, which may not apply to a real browser session). Those
  are left as plain landing pages rather than shipping a confidently-wrong
  prefilled URL. Expedia's car deep link needs a numeric `dpln` region ID
  for a fully prefilled result that this project doesn't have a way to look
  up, so it's best-effort (usually lands on a disambiguation step instead).
- **No existing MCP server solves this better for free.** Researched
  existing options first: the official Expedia MCP needs partner-API
  credentials: Skyscanner MCP projects are universally described by their
  own authors as "reverse-engineered, unofficial," or fall back to deep
  links; nothing covers Priceline at all; commercial options (e.g. RollingGo)
  are closed-source with unclear licensing. `fast-hotels` was the one
  genuine find -- a real, open-source, pip-installable library nobody had
  surfaced in that research, needing only the `primp` compatibility patch
  above to work.

### Sandbox (shell & files, contained to the container)
| Tool | What it does |
|---|---|
| `run_command(command, timeout)` | Run a shell command, cwd = `/workspace`. Full shell access *within the container* -- the container is the sandbox boundary, there's no further in-container jail. |
| `read_file(path)` / `write_file(path, content, append)` / `list_dir(path)` / `delete_path(path)` | File ops scoped to `/workspace`, blocks path traversal outside it. |

### Coding
| Tool | What it does |
|---|---|
| `run_python(code, timeout)` | Run a Python snippet as its own subprocess (`python3 -c`), clean stdout/stderr/exit-code separation. Not a persistent REPL -- no state survives between calls. |
| `lint_python(path)` | Lint Python files with `ruff check`. |
| `format_python(path, check)` | Format Python files with `ruff format`. `check=True` (default) only previews a diff; `check=False` applies it. |

Only Python tooling is installed -- no Node/Go/Rust runtimes, to keep the
image lightweight. Packages installed at runtime via `run_command` (`pip
install ...`) don't survive a container rebuild; only `/workspace` persists.

### Git
| Tool | What it does |
|---|---|
| `git_clone(url, path)` / `git_status(path)` / `git_log(path, max_count)` / `git_diff(path, staged)` / `git_pull(path)` / `git_add(path, files)` / `git_commit(message, path)` / `git_branch(path)` | Thin wrapper over the `git` CLI, scoped to `/workspace`. Commit identity comes from `GIT_AUTHOR_NAME`/`_EMAIL`/`GIT_COMMITTER_NAME`/`_EMAIL` env vars. Push/private-repo auth is intentionally out of scope -- that needs real credentials (SSH key or token) mounted in, a bigger decision than this wrapper should make silently. |

### Database
| Tool | What it does |
|---|---|
| `db_query(sql, params, database)` | Read-only query (SELECT/PRAGMA/WITH only) against a SQLite database in `/workspace/.db/<name>.db`. |
| `db_execute(sql, params, database)` | Writes (CREATE/INSERT/UPDATE/DELETE/etc). |
| `db_list_tables(database)` / `db_schema(table, database)` | Introspection. |

Zero new dependencies -- `sqlite3` is Python stdlib. Multiple named databases
supported via the `database` param (default `"default"`), sanitized against
path traversal.

### Content & knowledge
| Tool | What it does |
|---|---|
| `read_pdf(source, max_chars)` | Extract text from a PDF -- `source` can be a URL or a path in `/workspace`. Pure-Python (`pypdf`), fully offline once the bytes are in hand. |
| `get_youtube_transcript(video, max_chars)` | Get a YouTube video's transcript. Accepts a full URL or a bare video ID. |
| `wikipedia_lookup(query, sentences)` | Short authoritative summary + article URL via Wikipedia's official API. |
| `kb_index(url, name)` / `kb_search(query, name, max_results)` | Fetch a page (via `fetch_url`) and index it into a local SQLite FTS5 knowledge base; search it later (BM25-ranked) instead of re-fetching or re-pasting the same large page repeatedly. Zero new dependencies (`sqlite3` is stdlib). Multiple terms in a search are ANDed with no stemming -- "coroutine" won't match "coroutines"; prefer a few simple terms. |

### Memory
| Tool | What it does |
|---|---|
| `remember(key, value)` / `recall(key)` / `list_memories()` / `forget(key)` | Simple JSON-backed key/value notes, persisted in the same `/workspace` volume, survives container restarts. |

### Toolbox
| Tool | What it does |
|---|---|
| `convert_units(value, from_unit, to_unit)` | Length (m/ft/km/mi/cm/in), weight (kg/lb/g/oz), temperature (c/f/k). Pure arithmetic, offline. |
| `zip_files(paths, output_path)` / `unzip_file(zip_path, output_dir)` | Archive/extract files in `/workspace`. stdlib `zipfile`. |
| `generate_qr_code(data, output_path)` | QR code as SVG, saved in `/workspace`. Fully offline -- no network call, and no Pillow dependency needed (SVG render mode). |

### Local LLM bridge
| Tool | What it does |
|---|---|
| `ask_local_llm(prompt, system, backend, max_tokens, temperature)` | Calls your own LM Studio and/or MLX server (`lmstudio_server.sh` / `mlx_server.sh`) via their OpenAI-compatible APIs. `backend="auto"` tries LM Studio then MLX. |

**On `LOCAL_LLM_MODEL`: leave it unset.** Your MLX server reports raw HuggingFace
repo IDs (`mlx-community/Qwen3-30B-A3B-4bit`), LM Studio reports its own catalog
names (`qwen/qwen3.5-9b`), and Pi's `pi_models.json` aliases both of those to yet
a third naming scheme (`qwen3-30b-moe`) -- no single hardcoded value is correct
for both backends. Auto-detect (query the backend's own `/models`, use what it
reports) is actually more correct than pinning a value, since it always matches
whatever's actually loaded and adapts when you switch models via
`mlx_server.sh`'s M1/M2/M3 configs. If LM Studio ever has multiple models loaded
at once and you need to pin a specific one, use `LMSTUDIO_MODEL`/`MLX_MODEL`
(per-backend, since the id formats differ) rather than the shared
`LOCAL_LLM_MODEL`.

## Configuration

Nothing meaningful is hardcoded, and config is deliberately tiered so you
only have to look at what actually matters for your setup:

1. **Copy `env.example` to `.env`** and fill in the handful of settings
   there -- that file lists *only* what's worth reviewing per-deployment
   (your SearXNG URL, your local LLM endpoints, optionally your git identity).
2. **Everything else already has a sensible default**, organized into two
   more sections directly in `docker-compose.yml` (not duplicated in this
   README -- that file's comments are the source of truth, one comment per
   variable explaining what it does and when to touch it):
   - **ADVANCED** -- timeouts, browser settings, local-LLM model pins. Fine
     to never touch; add a line to `.env` only if you want to override one.
   - **SKILL TOGGLES** -- one `SKILL_<NAME>_ENABLED=true` per skill. Set any
     to `false` to hide that skill's tools from the MCP tool list entirely
     (the module isn't even imported). **One nuance:** disabling a skill
     only hides *its own* tools -- it doesn't stop other enabled skills from
     importing its plain functions directly. `itinerary.plan_trip` still
     calls `flights`/`weather`/`web_search`'s functions even if those three
     are individually disabled (it imports them directly, so Python resolves
     the import regardless); same for `git`/`coding` reusing `sandbox`'s
     path-safety helpers. If you need `plan_trip` to truly lose flight data,
     disable `itinerary` itself, not just `flights`.

Resource limits (`mem_limit: 1g`, `cpus: 1.0`) live in `docker-compose.yml`
directly (not as env vars), since they're compose-level, not
application-level, settings.

## Running it

```bash
cp .env.example .env   # edit as needed
docker compose up -d --build
```

Other machines on your LAN reach it at `http://<host>:8088/sse` (replace
`<host>` with this machine's LAN IP).

> **If the box running this container is different from the Mac running
> `lmstudio_server.sh`/`mlx_server.sh`** (likely -- that's probably also your
> SearXNG box, and MLX only runs on Apple Silicon Macs): the local LLM
> bridge's defaults (`host.docker.internal`) resolve to whatever machine is
> *running the container*, not to your Mac. Override them in `.env` to that
> Mac's actual LAN IP instead, e.g.:
> ```
> LMSTUDIO_URL=http://<your-mac's-lan-ip>:1234/v1
> MLX_URL=http://<your-mac's-lan-ip>:8080/v1
> ```
> `SEARXNG_URL` doesn't have this problem -- it's already a full LAN address,
> not `localhost`/`host.docker.internal`, so it works unchanged regardless of
> which box runs the container.

## Adding a new skill

1. Create `skills/my_skill.py`.
2. Define your tool(s) as plain module-level functions (async if they do
   I/O), with a docstring -- that becomes the tool's description to the LLM.
3. Add `def register(mcp): mcp.tool()(my_function)` at the bottom.
4. `docker compose up -d --build`.

That's it -- no changes to `server.py` needed. See `skills/utils.py` for a
simple example, or `skills/itinerary.py` for one that imports and composes
other skills' functions directly.

## Connecting agents

### Pi coding agent

Official MCP extension: [pi-mcp-extension](https://pi.dev/packages/pi-mcp-extension).

```bash
pi install npm:pi-mcp-extension
```

Add to `~/.pi/agent/mcp.json` (global) or `.pi/mcp.json` (per-project) -- either
transport works, same server/tools either way:

```json
{
  "mcpServers": {
    "mcp-ultimate": {
      "transport": "sse",
      "url": "http://<host>:8088/sse",
      "lifecycle": "eager"
    }
  }
}
```

Or, for Streamable HTTP instead:

```json
{
  "mcpServers": {
    "mcp-ultimate": {
      "transport": "streamable-http",
      "url": "http://<host>:8088/mcp",
      "lifecycle": "eager"
    }
  }
}
```

`lifecycle: "eager"` connects on startup; use `"lazy"` if you'd rather start
it on demand with `/mcp:start`. Restart Pi (or reload its MCP config) and its
49 tools should appear alongside your built-in `read`/`write`/`edit`/`bash`.

### Hermes Agent

Official docs: [MCP Config Reference](https://hermes-agent.nousresearch.com/docs/reference/mcp-config-reference), [Use MCP with Hermes](https://hermes-agent.nousresearch.com/docs/guides/use-mcp-with-hermes).

Add to `~/.hermes/config.yaml`:

```yaml
mcp_servers:
  mcp_ultimate:
    url: "http://<host>:8088/sse"
    transport: "sse"
    enabled: true
    timeout: 120
    connect_timeout: 60
```

Hermes defaults to Streamable HTTP and treats `transport: "sse"` as opting
into the legacy transport -- to use Streamable HTTP instead, point `url` at
`/mcp` and drop the `transport` line entirely (or set it explicitly to
`"streamable-http"`):

```yaml
mcp_servers:
  mcp_ultimate:
    url: "http://<host>:8088/mcp"
    enabled: true
    timeout: 120
    connect_timeout: 60
```

Then, from a running `hermes chat` session, reload without restarting:

```
/reload-mcp
```

Or verify connectivity directly from the shell:

```bash
hermes mcp test mcp_ultimate
```

Hermes' docs recommend `tools.include: [...]` to whitelist a minimal tool
set rather than exposing all 49 by default, especially since `run_command`
has unrestricted shell access inside the container -- worth doing here if
Hermes will be driving this server autonomously. You can also cut the
exposed surface at the source with this server's own
[`SKILL_*_ENABLED` switches](#enabledisable-skills) instead of (or alongside)
Hermes' `tools.include`.

## Dependency policy

`requirements.txt` is deliberately left unpinned so every `docker compose up
-d --build` picks up the latest release of each package -- no version drift
to manually bump. One exception, with a comment explaining it right in the
file: `mcp` is capped at `<2.0.0` because `mcp` 2.x renamed `FastMCP` to
`MCPServer`, a confirmed breaking change against this codebase (hit and
diagnosed directly during development). Removing that cap will break
`server.py` outright the next time pip resolves `mcp>=2.0`, not just degrade
something gracefully.

The real cost of "always latest" showed up almost immediately: deploying to a
second machine pulled a newer `selectolax` than the one this was developed
against, which deprecated the `Modest` backend `skills/utils.py` imported
(`from selectolax.parser import HTMLParser`), crash-looping the container.
Fixed by switching to the non-deprecated `from selectolax.lexbor import
LexborHTMLParser` (API is otherwise identical). This is the shape of risk
you're signing up for with unpinned deps in general -- things work today and
can break on the next rebuild when an upstream package makes a breaking
change, with no warning beyond the crash itself. `fast-flights` in particular
is a small, community-run package with a history of internal API churn
(`FlightQuery`/`Passengers`/`create_filter`/`get_flights`) -- if a rebuild
breaks `search_flights`/`plan_trip` specifically, that's the first place to
check. `playwright` is unpinned but safe: the Dockerfile's `playwright
install` step always downloads the browser build matching whatever version
of the `playwright` *package* pip just resolved, in that same build step, so
the two can't drift apart from each other even though neither is pinned.

## Known tradeoffs (read before relying on this in production)

- **`search_flights`/`search_hotels`/`search_car_rentals`/`search_packages`**
  scrape or deep-link against sites whose ToS prohibit automated access. They
  work today; they are not guaranteed to keep working. See "Travel sites:
  what's real vs. a link" above for exactly which parts are real scraped
  data, confirmed deep links, or best-effort/unconfirmed links, per site.
- **`browse`** ships a full headless Chromium -- most of the image's 1.54GB.
  It also still identifies itself as headless at the protocol level: Chromium
  generates its `Sec-Ch-Ua` Client Hints header from the actual browser
  binary (e.g. `"HeadlessChrome";v="156"`), independent of whatever
  `User-Agent` we send -- our header/UA randomization doesn't touch this.
  Fixing it means patching the kind of automation fingerprint (headed mode,
  branded Chrome, `--disable-blink-features=AutomationControlled`, etc.)
  that's specifically about hiding automation from detection, not sending
  realistic headers, so it's deliberately not done here -- same call made for
  dropping `browser_search` against DuckDuckGo.
- **`run_command`** is real, unrestricted shell access *inside the
  container*. The container (no host mounts, non-root user) is the security
  boundary, not anything inside it.
- **`ask_local_llm`** requires you to actually start `lmstudio_server.sh` or
  `mlx_server.sh` on the host first -- it fails gracefully with a clear
  message if neither is reachable.
