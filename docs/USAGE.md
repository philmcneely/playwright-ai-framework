"""
NOTE: plain Markdown doc (the triple-quote is not code — GitHub renders this as
Markdown). Using the AI test agents & the heal CLI for this pytest framework.
"""

# Using the AI test agents & the heal CLI (Python / pytest)

Two ways to put a model to work. Pick by whether you want a model **in an
interactive loop** (authoring/triage) or a **headless, pick-any-model call**
(CI / nightly automation).

| | Path 1 — Claude Code + MCP agents | Path 2 — the `heal` CLI |
|---|---|---|
| Model | the agent loop host (Claude; or opencode/codex → any model) | none in this repo: the heal service owns the model settings |
| Needs | Claude Code (or another loop host) | Python + a running heal service — no Claude Code |
| Best for | authoring tests, judgment-heavy healing | CI / nightly / unattended healing |

> Playwright's official Test Agents are JS/TS-only. The agents here are a **port**
> for pytest: same prompts/flow, but the healer runs `pytest` in the shell and
> grounds in a real browser via the bundled **`playwright mcp`** (browser MCP) —
> there is no `run-test-mcp-server` in the Python package.

---

## Path 1 — Claude Code + the MCP agents (planner / generator / healer)

See `.claude/agents/*.md` and `.mcp.json` (points at `playwright mcp`).

```bash
cd <this repo>
claude            # launch Claude Code in the repo
```

Claude Code auto-reads **`.mcp.json`** → starts the Playwright browser MCP server
and loads the three subagents. Drive them conversationally:

- **Plan** — "Use the playwright-test-planner agent to explore the app and write a
  test plan." → explores via accessibility snapshots, writes Markdown to `specs/`.
- **Generate** — "Use the playwright-test-generator agent to turn `specs/<plan>.md`
  into pytest tests." → drives a real browser via MCP and writes `test_*.py` files
  (matching this repo's async + page-object conventions).
- **Heal** — "Use the playwright-test-healer agent to fix the failing tests." →
  runs `pytest`, reproduces each failure in the browser, updates **locators only**
  (never intent), re-runs until green; uses `pytest.skip(...)` (the `test.fixme()`
  equivalent) only when confident the test is right and the app is at fault.

**Use a different model to drive the agents:** point an `opencode`/`codex` loop at
any OpenAI-compatible endpoint (OpenRouter, a local server, our Qwen).

---

## Path 2 — the `heal` CLI (headless, backed by the heal service)

`scripts/heal.py` is the out-of-band healer — the engine the overnight job uses,
and usable on demand. **No Claude Code required, and no model code in this
repo.** The CLI is a client of the **heal service** (`heal-service`, a separate
project): the service owns the model calls and the healing rules (which element,
which locator, language branches, healed or needs-human). The CLI runs the tests,
gathers evidence, applies the patch the service returns, and re-runs to verify.

```bash
BASE_URL=<app-url> \
HEAL_SERVICE_URL=http://localhost:8765 \
[HEAL_SERVICE_TOKEN=<token>] \
python scripts/heal.py [-k <name>] [--max N] [--open-pr]
```

Per failing test: run it → send the stack files, the element inventory of the
reopened failing route (collected with the service's own probe script), the page
language and, when recorded, the last green run's fingerprint → the service
answers with a candidate → the CLI checks it **in the live page (exactly one
match, the expected element) before editing anything** → applies the patch →
**re-runs the exact test** → reports back. A candidate that fails moves the
service to its next one; after the last, the test is flagged for a human. Locators
only; a failure it cannot make pass is reverted. `--open-pr` assembles one PR
with the decisions.

**What it prints and writes:** every decision with its token usage
(`healed`, `needs_human` with the service's reason, `not_drift`), a run total of
model calls and tokens, and `test_artifacts/heal-summary.json` (counts, usage and
every decision; `HEAL_ARTIFACTS_DIR` moves it). A failure past `--max`, a service
that cannot be reached, or an error reply is recorded as `needs_human` with the
reason; the run never stops on one failure.

**Safety:** the CLI applies a patch only when the file is one it sent and sits
under the source roots (`pages`, `tests`, `utils`; `HEAL_SOURCE_ROOTS` changes
them), the file's hash is unchanged since the service saw it, the span holds
exactly the text the service expected, and the replacement passes the local
validator (a chain of approved Playwright locator calls with literal arguments on
the same receiver; each branch of a language switch is checked on its own). Only
the diagnosed occurrence is edited, and an edit is kept only if the exact target
test ran *and* passed *and* the service confirms the heal. The service never sees
input values, cookies or storage state, and this client sends **no screenshot**
(vision is off: `HEAL_VISION` and `HEAL_MASK` are accepted and unused for now).
`--open-pr` requires a clean working tree and commits only the healed files. For
pages behind login, set `HEAL_STORAGE_STATE=<playwright storage-state.json>` so
the page is opened as a signed-in user (the file stays on this machine).

**Settings:**

| Variable | Meaning |
|---|---|
| `HEAL_SERVICE_URL` | the heal service, for example `http://localhost:8765` (required) |
| `HEAL_SERVICE_TOKEN` | bearer token, when the service requires one |
| `HEAL_TEST_ID_ATTRIBUTE` | your project's test id attribute (default `data-testid`); `get_by_test_id` is only written when it matches |
| `HEAL_SOURCE_ROOTS` | comma separated source roots (default `pages,tests,utils`) |
| `HEAL_STORAGE_STATE` | storage-state file for pages behind login |
| `HEAL_ARTIFACTS_DIR` | where `heal-summary.json` goes (default `test_artifacts`) |
| `HEAL_VISION`, `HEAL_MASK` | accepted; unused until vision lands |

**Language branches.** When a locator depends on page copy and the page is now in
another language than the last green run, the service returns code that switches
on the page language:

```python
by_language(self.page, {"en": self.page.get_by_label('Username'), "fr": self.page.get_by_label("Nom d'utilisateur")})
```

`by_language` ships in `utils/heal_locale.py`; the CLI adds the import to a file
that receives such code. It returns the entry for the page's language, and the
first entry (the original copy) for any other language; copy is never translated.
On an async page the language is the one `track_language(page)` recorded (the
`page` fixture in `conftest.py` calls it).

### Fingerprints (optional): let the service skip the model

With **`HEAL_FINGERPRINTS=on`**, a pytest plugin (`utils/heal_fingerprints.py`,
registered in `conftest.py`) records, for each locator a **clean green** test acts
on, what the page probe sees of the element (attributes, copy, box, frame, page
path, language; never input values), plus the other elements recorded on the same
page. At heal time the CLI sends that as `last_pass`, and the service can often
settle the element with no model call. A fingerprint is written only from a test
that passed once (no rerun), is not flaky and is not running inside a heal. It is
off by default and then costs nothing.

```bash
HEAL_FINGERPRINTS=on HEAL_SERVICE_URL=http://localhost:8765 pytest        # on the green run (CI: default branch)
```

The cache is `.heal/fingerprints.json` (override the folder with `HEAL_DIR`),
written atomically; `.heal/.gitignore` containing `*` is written for you, so it is
never committed by accident. Fingerprints change with app versions and viewport
size, so keep `.heal/` as a CI cache from the last green run on the default branch
rather than in git. **Opt in to committing it** with
`HEAL_FINGERPRINTS_COMMIT=on` (the ignore file is then not created); expect churn.
The probe script is the vendored `utils/heal_probe.js`; it is never fetched and cached
from the service (`HEAL_PROBE_FROM_SERVICE=1` uses the service's copy only when it is
byte-identical). Fingerprints store element copy (text, labels, rows), which can hold
personal data; set `HEAL_FINGERPRINT_COPY=off` to store hashes of the copy instead.
`HEAL_DIR` and `HEAL_SOURCE_ROOTS` must be relative paths inside the repository.

**Known limits:** the page is reopened at the failing route as first loaded, so an
element that only appears after a click or login step may be missing from the
inventory (set `HEAL_STORAGE_STATE` for login); only locators the test acts on
(`click`, `fill`, `check`, `select_option`, ...) are fingerprinted.

> This repo also keeps a **legacy** in-run Ollama healer (the `conftest.py`
> AI-healing hooks + `AI_HEALING_ENABLED`). That is the older "heal during the
> run" approach; the agents + `heal.py` above are the v2 out-of-band replacement.

---

## Writing a new test (author workflow)

### A. You have a capable agent (Claude Code, or opencode/codex on a real model)
1. **Plan** — ask the planner agent to explore the feature; it writes
   `specs/<feature>.md`. Review and trim it — a human gate.
2. **Generate** — ask the generator agent to turn a plan item into a test; it
   drives the browser via MCP and writes `tests/.../test_<name>.py` matching this
   repo's async + page-object conventions.
3. **Review** — read the generated test (never merge blind); assert
   behavior/structure, not pinned data.
4. **Run** `pytest`. The **healer** then maintains locators when the UI drifts.

### B. No agent, or a token-limited one (e.g. Copilot on a tight budget)
No LLM needed to author — record, then refactor:
1. **Record (zero tokens)** — `playwright codegen --target python-pytest <url>`;
   click through the flow and it writes a working pytest test with real locators.
2. **Refactor to conventions** — move locators into a page object under `pages/`,
   prefer the resilient hierarchy `get_by_role` → `get_by_label` →
   `get_by_placeholder` → `get_by_text` → `get_by_test_id` → CSS/XPath (last
   resort), and keep assertions about **structure/behavior, not specific data**.
3. **Spend the limited agent sparingly** — one focused prompt ("turn this recorded
   flow into a page object + test matching `pages/login_page.py`") costs a fraction
   of an explore/generate loop. Don't use it to *explore*.
4. **Maintenance stays cheap** — the `heal.py` CLI runs only on failures and can
   talk to a heal service that you point at a **local/cheap model**, so keeping tests
   green never burns your agent budget.

Conventions either way: one feature per test module, pytest markers, resilient
semantic locators, data-agnostic assertions, and page objects for anything reused.

## Which path?
- **Authoring new tests / interactive triage** → Path 1 (Claude Code + agents).
- **CI, nightly, unattended, swap models in one place (the service)** → Path 2 (the `heal` CLI).

---

## Tags, reports and retries (standard conventions)

### Tags (markers) and filtering
Tag a test with any number of `@pytest.mark.<name>` and select with `-m`.

| Kind | Markers |
|---|---|
| Suite | `smoke`, `regression` |
| Priority | `p0` (critical) `p1` `p2` `p3` |
| Type | `positive`, `negative`, `boundary` |
| Dependency | `llm` (needs an LLM / AI service) |
| **Feature** | anything you like: `login`, `cart`, `checkout`, ... |

Feature markers need **no registration**: `conftest.py` scans the test paths at
startup and registers every `pytest.mark.<name>` it finds, so `pytest -m cart`
works with no "unknown marker" warning. Standard markers are documented in
`pytest.ini`. (`--strict-markers` is intentionally off for this reason, so
double-check marker spelling.)

```bash
pytest -m smoke                     # all smoke tests
pytest -m login                     # one feature
pytest -m "smoke and login"         # intersection
pytest -m "login and negative"      # negative login cases
pytest -m "p0 or p1"                # priority tiers
pytest -m "not llm and not visual"  # skip AI/visual tests
pytest --collect-only -q -m smoke   # preview what a filter selects
```

### Reports and artifacts (all under `results/`)
Enabled by default via `addopts` in `pytest.ini`:

| Output | Path |
|---|---|
| JUnit XML (CI ingestion) | `results/junit.xml` |
| Self-contained HTML report | `results/report.html` |
| Playwright trace (`retain-on-failure`) | `results/artifacts/<test>.trace.zip` - open with `playwright show-trace` |
| Screenshot (`only-on-failure`) | `results/artifacts/<test>.png` |
| Allure results (optional) | `results/allure/` |
| Console | verbose, short tracebacks |

**Allure** (`allure-pytest`) writes raw results to `results/allure/` on every
run; the Allure CLI is only needed to *render* them, so CI does not require it:

```bash
allure serve results/allure                          # open interactively
allure generate results/allure -o results/allure-report --clean --single-file
```
Install the CLI separately (`brew install allure`, or the release tarball).
Override any
option on the command line, e.g. `--tracing=on`, `--screenshot=off`,
`--junitxml=out.xml`, `--output=some/dir`.

### Retries
Flaky-test retries use `pytest-rerunfailures`. Default is **0** (no retries):

```bash
pytest --reruns 2                       # retry failures up to 2 times
pytest --reruns 2 --reruns-delay 5      # wait 5s between attempts
pytest -m smoke --reruns 2 -n auto
```
Retried tests show as `RERUN` in the console/HTML report, and traces are kept
for failed attempts. Mark a single known-flaky test with
`@pytest.mark.flaky(reruns=3)`.

---

## Data setup & teardown

Reusable fixtures in `utils/data_seeding.py` (registered in `conftest.py`). All
configuration comes from the environment; nothing is hardcoded, and each helper
skips or no-ops when it is not configured.

| Env var | Purpose |
|---|---|
| `SEED_API_BASE_URL` | Base URL of the API used to seed data (`api_seed` skips the test if unset) |
| `SEED_API_TOKEN` | Optional bearer token |
| `SEED_DB_DSN` | Optional DSN: `sqlite:///path.db`, or `postgresql://...` (needs `psycopg`). Unset = `db_seed` is a no-op |

| Fixture | Scope | What it gives you |
|---|---|---|
| `cleanup` | function | Registry: `cleanup.register("desc", fn)`; callbacks run **LIFO** after the test, all of them even if one fails (failures are reported together) |
| `session_cleanup` | session | Same, for shared data removed once at session end |
| `api_seed` | function | HTTP client: `create(path, payload)` POSTs and schedules `DELETE <path>/<id>` for teardown; also `delete(path)` and `reset(path)` |
| `db_seed` | function | `run_script(sql)`, `execute(sql, params)`, `reset("table", ...)`; no-op without a DSN |

### Pattern: yield-based setup -> teardown
```python
@pytest.fixture
def order(api_seed, cleanup):
    created = api_seed.create("/orders", {"sku": "demo"})   # setup; auto-deleted
    cleanup.register("flush cache", lambda: flush_cache())  # extra teardown
    yield created                                           # test runs here
    # code after yield also runs as teardown, pass or fail
```
Prefer registering a cleanup right after each create so a failure halfway
through setup still removes what exists. Example: `tests/test_data_seeding_example.py`
(`SEED_API_BASE_URL=... pytest -m seeding`).
