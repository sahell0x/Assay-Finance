# Assay

**Assay** (formerly Equity Research Agent) is an automated equity research analyst. Enter a ticker and it pulls the company's financial
statements, computes every ratio in Python, retrieves qualitative context from SEC filings
and newswires by vector search, and produces a structured investment memo with a
BUY/HOLD/SELL recommendation and a citation behind every claim it makes about the world.
The language model writes the argument; it never produces a number and never chooses the
rating.

---

## The one design decision that shapes everything else

**The model never computes a number.**

A language model producing a figure and a language model producing a *plausible-looking*
figure are indistinguishable from the outside. So the arithmetic and the prose are kept in
separate halves of the system, and the boundary is enforced rather than trusted:

- `backend/src/analytics/` is pure. `ratios.py`, `trends.py` and `scoring.py` are
  functions over plain dicts that import nothing from the agent, the model layer, or the
  database. Every figure the product reports comes from there.
- The model receives those results **already formatted as strings**, with an instruction
  that says the table is the only source of numbers it may use.
- Afterwards, every percentage, multiple and currency figure in the generated text is
  regexed out and matched numerically against computed state. A transposed digit — 31.5%
  becoming 35.1% — fails verification and sends the memo back for one revision. This runs
  in Python, because a model re-reading its own draft is the wrong instrument for catching
  the mistake it just made.
- The interface then lets you check it yourself: **every metric row opens into the formula
  that produce
---d it and the statement lines that fed it.**

Two companion rules fall out of the same principle:

**The rating comes from a rubric, not from the model.** A deterministic scorecard maps each
metric onto 0-10 by interpolation between named anchors, folds those into five weighted
dimensions, and applies two thresholds. It runs *before* the memo is written. The model is
told the rating and asked to argue for it; if it disagrees it must say so in the caveats,
where a reader can see the disagreement rather than have it silently override the
arithmetic. The interface draws the scale and marks where the score landed, so the
determinism is visible instead of asserted.

**Every qualitative claim carries a citation.** Sentences making a claim about competition,
regulation, management or demand must end with a `[S3]` tag naming a retrieved passage.
Python then checks: sentences with no tag, or with a tag pointing at a source that does not
exist, are removed before the memo is stored. The citation rate is recorded and shown on
the trace tab of every analysis.

**The rubric runs backwards.** Because the rating comes from tables and a pure fold
rather than from a model, it can be asked the inverse question — *what would have to be
true for this to be a BUY?* — and answer it exactly. The **Scenario** tab solves each
metric for the smallest move that would cross a band, says plainly which metrics cannot
get there on their own, and lets you drag any of them to check the answer. Share price is
one of the levers, and moving it moves six valuation multiples at once, each by its own
law: P/E and price/book scale with the price, EV multiples scale with enterprise value
because net debt does not move, and FCF yield moves the other way.

It costs nothing to run. Every input it needs is already in the stored scorecard, so a
scenario is one database read and a fold over five dimensions — no data fetch, no model
call, no queue slot, no quota. And it recomputes through the same `scoring.py` the
pipeline used rather than a copy of the rules in the browser, so the panel can never
disagree with the memo beside it.

---

## Architecture

```
Browser ──POST /analyses──▶ FastAPI ──enqueue──▶ Redis ──▶ ARQ worker (max_jobs=1)
   ▲                           │                                    │
   └────SSE, node events───────┴──────Redis pub/sub─────────────────┘

                         LangGraph pipeline
  ingest → validate → profitability → liquidity → growth → peers → news_rag
                                                                      │
                                                    scorecard ◀───────┘
                                                        │
                                                      memo ⇄ critic  (one revision)
                                                        │
                                              Postgres + pgvector
```

Two orderings are load-bearing:

- **`peers` runs after the company nodes** because it writes back. Once peer values exist,
  every metric already computed gets a percentile stamped onto it, which turns "operating
  margin is 31%" into "operating margin is 31%, better than 88% of its comparables".
- **`news_rag` runs after `peers`** because its queries are *conditioned on what the numbers
  found*. Four themed queries always run — competition, guidance, regulation, costs — and
  more are added only when the arithmetic warrants: revenue fell, so search for demand
  weakness; net debt is above three turns of EBITDA, so search for refinancing and
  covenants; margins compressed, so search for input costs. A retrieval stage that does not
  know revenue fell cannot go looking for the reason.

---

## Running it

You need Docker and an API key. Nothing else.

```bash
git clone <this-repo> && cd equity-research-agent
cp backend/.env.example backend/.env      # then put your key in it
cp frontend/.env.example frontend/.env
docker compose up --build
```

The interface is at http://localhost:3000, the API at http://localhost:8000 (`/docs` for
the OpenAPI browser). Migrations run automatically on first boot.

`make help` lists every target. The two worth knowing before you start:

```bash
make doctor    # preflight: config, postgres, redis, your model provider, network, corpus
make seed      # pre-build the retrieval corpus for ~20 popular tickers
```

**Run `make doctor` first.** It checks every setting that can be wrong and tells you what
to change, rather than letting you discover it ninety seconds into an analysis. It
verifies your provider by making one real chat call and one real embedding call, and
confirms the embedding width matches the `halfvec` column.

### Backend and frontend each have their own compose file

```bash
docker compose up --build                    # everything, from the repo root
cd backend  && docker compose up --build     # db + redis + api + worker only
cd frontend && docker compose up --build     # the Next server only
docker compose up db redis                   # datastores only, apps run natively
```

The root file assembles the other two with Compose's `include`, so all three stay
runnable and there is one definition of each service. The backend's entire configuration
surface comes from `backend/.env` through `env_file`; `DATABASE_URL` and `REDIS_URL` are
deliberately re-stated in `environment:` so they resolve to the compose service names,
because the values in `.env` point at localhost for running natively.

To point the frontend at a different API you must **rebuild**, not restart —
`NEXT_PUBLIC_*` is inlined into the JavaScript bundle at build time. Put that value in
`frontend/.env` rather than passing it on the command line.

### Deploying

Production runs with two public subdomains on the same server:

```text
https://app.xyz.in  -> frontend container on port 3000
https://api.xyz.in  -> backend container on port 8000
```

Create the backend env file:

```bash
cp backend/.env.example backend/.env
```

Set these in `backend/.env`:

```ini
ENV=prod
OPENAI_API_KEY=...
AUTH_SECRET=<openssl rand -hex 32>
IP_HASH_SALT=<openssl rand -hex 16>
COOKIE_SECURE=true
COOKIE_DOMAIN=.xyz.in
CORS_ORIGINS=https://app.xyz.in
FRONTEND_URL=https://app.xyz.in
API_PUBLIC_URL=https://api.xyz.in
API_HOST_PORT=8000
```

Create the frontend env file:

```bash
cp frontend/.env.example frontend/.env
```

Set these in `frontend/.env`:

```ini
NEXT_PUBLIC_API_URL=https://api.xyz.in
BACKEND_URL=http://api:8000
WEB_HOST_PORT=3000
```

Start everything from the repo root:

```bash
docker compose up -d --build
```

The root compose file starts Postgres, Redis, the API, the worker and the frontend
together. Point Nginx like this:

```text
app.xyz.in  -> http://127.0.0.1:3000
api.xyz.in  -> http://127.0.0.1:8000
```

Because `NEXT_PUBLIC_API_URL` is baked into the frontend build, rebuild the frontend
container after changing `frontend/.env`:

```bash
docker compose up -d --build web
```

After deploy, check the containers and logs:

```bash
docker compose ps
docker compose logs -f --tail=100
```

**The server refuses to start in production without a real `AUTH_SECRET`** (32+ random
characters, not the example placeholder): sessions are signed with it, and a guessable
secret would let anyone sign in as anyone. With `ENV=prod` the interactive API docs at
`/docs` are also switched off.

Two more settings are worth adding before real users arrive:

```ini
# Password reset emails. Any SMTP provider (Postmark, SES, Resend, Mailgun, Gmail).
SMTP_HOST=smtp.postmarkapp.com
SMTP_USER=...
SMTP_PASSWORD=...
SMTP_FROM=Equity Research <no-reply@equity.sahell.in>

# Crash reports from the API, the worker and the browser. Free tier is plenty.
SENTRY_DSN=https://...@....ingest.sentry.io/...
```

Without SMTP, "Forgot password?" still works but the link is only written to the API log.
Without Sentry, errors still go to the container logs.

`ENV=prod` also switches the database to `NullPool`. That is deliberate for a serverless
Postgres like Neon, which bills while a connection keeps the endpoint awake — a
persistent idle pool burns the monthly allowance around the clock. On a always-on
Postgres you may want a real pool instead.

### Selling credits (Razorpay, test mode)

Free credits are one-time, never monthly: 3 without an account, and 10 more when you
create one (`ANON_RUN_LIMIT`, `FREE_ACCOUNT_CREDITS`). Runs made before signing up do
not eat into the account's 10. Signed-in users can also buy packs at `/credits`: Starter
(2 credits for ₹29), Pro (5 for ₹59) and Power (10 for ₹99). Free credits are always
spent first, nothing expires, and a run that fails gives its credit back.

The same page is the account's billing view: available balance, totals (analyses run,
credits bought, amount paid, credits given back), a 30-day usage chart split into free
and bought, a filterable activity log with CSV export (`/billing/activity.csv`), and a
payments list with each Razorpay reference and outcome (paid, not completed, refunded).

**The shop runs in Razorpay test mode on purpose.** The whole flow is the production
one: server-created orders, Razorpay Checkout, signature verification, webhooks and
refunds. It runs on test keys, so no money moves, and the page says so up front with
the test card details. Because every bought credit is still a real analysis on the model
bill, each account can make at most 3 purchases and buy at most 10 credits. An order
over the limit is refused before Checkout opens. A payment that still lands over it
(several orders opened, then all paid) adds nothing and is refunded through Razorpay.
With `PAYMENTS_TEST_MODE=true` a live key is refused outright.

Leave the keys blank and the shop simply says buying is not available yet. To switch it
on, add three lines to `backend/.env`:

```ini
RAZORPAY_KEY_ID=rzp_test_...        # Dashboard (Test Mode) → Account & Settings → API Keys
RAZORPAY_KEY_SECRET=...
RAZORPAY_WEBHOOK_SECRET=...         # the secret you type when adding the webhook
```

Then add a test-mode webhook in the Razorpay dashboard pointing at
`https://api.xyz.in/billing/webhook` for the `payment.captured` and `order.paid`
events, and run `make migrate` (migration `0003` adds the credit tables). To pay, use
card `4111 1111 1111 1111` with any future expiry and CVV, or the UPI id
`success@razorpay`.

Credits are granted as soon as the browser reports a correctly signed payment, and again
by the webhook if the customer closes the tab first. Both paths go through one locked
row, so a pack is never credited twice. Going live later means setting
`PAYMENTS_TEST_MODE=false`, using `rzp_live_` keys and choosing real prices in
`CREDIT_PACKS`.

### Which model provider

The app speaks the OpenAI API and nothing else, so anything that serves it will do.
Set three variables in `backend/.env` and nothing else changes:

| | `LLM_PROVIDER` | what else |
|---|---|---|
| **Official OpenAI** | `openai` | `OPENAI_API_KEY` |
| **Azure OpenAI** | `azure` | `OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_VERSION`. `MODEL_*` are **deployment names**, not model IDs |
| **Any compatible gateway** | `compatible` | `OPENAI_API_KEY`, `OPENAI_BASE_URL` (e.g. `https://aicredits.in/v1` — include the `/v1`) |

Two things this handles that catch people out:

- **Model IDs that do not exist on your provider.** The configured `MODEL_*` are verified
  against the provider's model list at startup and substituted from `MODEL_FALLBACKS` when
  absent. The substitution is logged and shown by `make doctor`. Azure is skipped, because
  it serves deployment names rather than model IDs.
- **Gateways that proxy chat but not embeddings**, which is common. `EMBEDDING_PROVIDER`,
  `EMBEDDING_API_KEY` and `EMBEDDING_BASE_URL` let embeddings go to a different provider
  than the chat traffic. Leave them blank for a single-provider setup.

**A misconfigured provider degrades, it does not crash.** Every figure in this product is
computed in pure Python and is untouched by the model being unreachable. If the key is
rejected or the base URL is wrong, the analysis still completes with every ratio, score,
chart and the rating intact; the prose falls back to text assembled from computed state,
and the memo says so in its caveats, naming the variable to fix.

### Developing on it

Everything in containers, everything reloading on save. **Nothing needs to be installed
on your machine** — no Python, no uv, no Node, no Postgres:

```bash
git clone <this-repo> && cd equity-research-agent
docker compose -f docker-compose.dev.yml up --build     # or: make dev
```

That is the whole setup. Postgres, Redis, the API, the worker and the frontend all come
up; migrations run on first boot; http://localhost:3000 works.

**You do not need a `.env` file to start.** Without one every setting falls back to a
working default and the system runs in offline mode: filings are fetched, every ratio,
score, chart and rating is computed, the interface is fully usable. Only the
model-written prose is a labelled placeholder. When you want the real thing:

```bash
cp backend/.env.example backend/.env    # add your OPENAI_API_KEY
docker compose -f docker-compose.dev.yml restart api worker
```

The source directories are bind-mounted, so an edit on your host restarts the right
service and nothing else — uvicorn watches `src/`, the worker runs `arq --watch src`,
and Next reloads itself. **The worker is the one that matters**: every node of the
analysis pipeline runs there, not in the API, so a change to a ratio or a prompt shows
up when the worker restarts.

```bash
make dev-logs ARGS=worker     # follow one service
make dev-shell ARGS=worker    # a shell inside it
make dev-down                 # stop; named volumes and your data stay
```

The dev stack publishes Postgres on **55433** and Redis on **6380**, deliberately
different from the production compose file, so both can run at once.

Emails the app sends (password reset) never leave your machine in development: they land
in **Mailpit**, a local inbox at http://localhost:8025.

One thing you will hit within an afternoon: the anonymous caps, three runs per cookie and
twelve per network per day. `make reset-quota` clears them; stored analyses are untouched.

<details>
<summary>Running it natively instead</summary>

Faster feedback and a real debugger, at the cost of installing things. Postgres 17+ with
`pgvector` and Redis 7, then:

```bash
make install
docker compose up db redis    # or point backend/.env at your own
make migrate && make doctor
make dev-backend              # and, in other terminals:
make dev-worker
make dev-frontend
```
</details>

## The stack

| | |
|---|---|
| **API** | FastAPI, fastapi-users with cookie sessions and optional Google OAuth |
| **Agent** | LangGraph — ten nodes, one conditional revision edge |
| **Analytics** | Pure Python over pandas. No LLM, no I/O, no framework |
| **Persistence** | PostgreSQL 17 + pgvector, SQLAlchemy 2.0 async, Alembic |
| **Providers** | OpenAI, Azure OpenAI, or any OpenAI-compatible gateway |
| **Queue** | Redis + ARQ, one job at a time, progress over pub/sub |
| **Retrieval** | `text-embedding-3-small` at 512 dimensions, stored as `halfvec`, HNSW cosine index |
| **Market data** | yfinance, behind a row-label alias resolver |
| **Filings** | SEC EDGAR submissions API, streamed and section-extracted |
| **Frontend** | Next.js App Router, TypeScript, Tailwind v4, TanStack Query, Recharts |
| **Tests** | pytest — 373, all offline |

---

## Details worth knowing about

**yfinance row labels are not stable.** They differ between tickers, between sectors and
between library versions. Nothing in this codebase indexes a statement frame directly;
every field goes through an alias resolver that walks a list of known labels, tolerates
duplicate index entries, and returns `None` rather than raising. Absence is a first-class
outcome recorded in a data-quality report, not an exception. Verified against three
genuinely different label sets: a hardware manufacturer, a bank, and a REIT.

**A 10-K is 10-20 MB of HTML.** Building a document tree over that peaks around half a
gigabyte, which is fatal on a 2 GB box also running Postgres connections and a worker. The
filing is consumed as a byte stream, tags are stripped incrementally with a carry buffer
so a tag spanning a chunk boundary is not mangled, and input is capped at 8 MB. Section
extraction takes the **last** match of `Item 1A` — the first is the table of contents, and
slicing from there is the single most common way filing extraction produces confident
nonsense.

**Risk factors are split per named risk.** Item 1A is a list of self-contained claims, so a
retrieval hit returns one whole risk rather than the tail of one and the head of the next.

**`halfvec(512)`, not `vector(1536)`.** Roughly a sixth of the storage for a retrieval
quality difference that does not show up at this corpus size. The 512 dimensions are
*requested from the API*, not sliced off a longer vector, so the result is natively
512-dimensional and correctly normalised — a truncated-and-not-renormalised slice would
quietly break cosine distance.

**Peer medians exclude non-meaningful multiples.** A peer whose EBITDA is barely positive
prints an EV/EBITDA in the hundreds or thousands of turns; that is a division artefact, not
a valuation. Research notes mark those "NM" and drop them, and so does this — both the
trimmed and untrimmed medians are shown, and the excluded readings are named rather than
quietly removed.

**The memo is the whole bill.** It is the only call that receives all four metric blocks
plus the full evidence set — about half the tokens of a run, and on the top-tier model it
was 84% of the cost, because that tier is 12x the input and 25x the output price of the
cheap one. The default routes it to the middle tier: **$4.14 per 1,000 analyses instead of
$10.42**. What that trades is prose quality alone — the rating comes from the rubric, the
figures are computed in Python, citations are enforced in Python, and the numeric verifier
runs either way. `make costs --compare` prices the options against your own runs.

Relatedly, a model fallback is chosen by **price**, not by size. The shipped chain used to
prefer the largest available model for the memo, which meant a missing top-tier ID fell
back to something costing more than the model it stood in for, with nothing saying so.

**Nothing runs in a request handler.** A full analysis takes 60-90 seconds. `POST /analyses`
returns `202` immediately; the worker publishes node-level progress to Redis pub/sub and an
SSE endpoint relays it. The stream replays a full snapshot on connect, so a mid-run refresh
rebuilds the checklist instead of showing ten empty rows for a job that is nearly done.

**Cached results still animate.** A cache hit clones the stored run *and its event
timeline*, then replays those events at an eighth of their recorded timings. The pipeline
visualisation is the most informative thing in the interface and a cache hit should not
throw it away. It is badged honestly as cached with the original date, alongside a control
to compute a fresh one.

**Anonymous visitors get the whole product.** Three runs, every tab, every chart, the trace.
The signup prompt appears *after* the third result has rendered, never before the first —
gating before output leaves a visitor with nothing to evaluate. Signing up migrates their
history across.

---

## Tests

```bash
make test                                 # backend: ~480 tests
cd backend && pytest -k "not api"         # skip the tests that need Postgres
cd frontend && npm test                   # frontend unit tests (Vitest)
cd frontend && npm run test:e2e           # browser tests (Playwright) against a running
                                          # dev stack; none of them spends API credit
```

The API tests need a Postgres to run against. With the dev stack up, point them at it:
`TEST_DATABASE_URL=postgresql+asyncpg://equity:equity@localhost:55433/equity_test make test`
(create the `equity_test` database once; the tests never touch your dev data).

The suite runs entirely offline. Notable parts:

- **Every ratio formula** is checked against hand-verified figures from Apple's FY2024
  10-K, with the derivation written out in a comment. A regression such as average equity
  quietly becoming ending equity fails the test rather than shifting a plausible number.
- **The alias resolver** is exercised against captured statement frames for five real
  companies whose labels genuinely differ.
- **Degenerate inputs** get their own file: negative shareholders' equity, zero and negative
  EBITDA, no interest expense, bank-shaped balance sheets, fewer than three annual periods,
  and absent peers. The rule under test throughout is that a ratio returns `None`, never
  `0`, `inf` or `NaN`.
- **Citation enforcement and numeric verification**, including a regression test for a real
  bug: a trailing `\b` after a stem like `compet` never matches inside "competition", which
  silently disabled half the citation check.
- **The HTTP contract** — that a run is never executed inline, that quota and budget are
  enforced before anything is enqueued, that a cache hit does not consume an allowance,
  and that a failed enqueue refunds the run.
- **One full graph integration test** with every external call mocked, asserting among
  other things that the rating on the finished memo is the rating the rubric produced.

---

## Repository

```
backend/
  src/analytics/     pure functions — the only place numbers are computed
  src/agent/         LangGraph state, nodes, model routing, progress
  src/data/          yfinance alias resolver, EDGAR streaming, chunking, pgvector
  src/api/           routes, auth, schemas, PDF
  src/core/          budget guard, cache, rate limits
  tests/             321 tests, no network
frontend/
  app/               routes
  components/        rating block, metric table, derivation strip, pipeline, charts
  lib/               API client, formatters, the SSE hook
  DESIGN.md          the design plan, its pre-build review, and the post-build critique
DECISIONS.md         every judgment call, with its reason
```

`DESIGN.md` and `DECISIONS.md` are the two files worth reading if you want to know why
something is the way it is. `DESIGN.md` in particular records the design plan as written
*before* any component, the revisions made to it on review, and an item-by-item critique of
the built interface afterwards.

---

This is a portfolio demonstration, not investment advice.
