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
| Model | the agent loop host (Claude; or opencode/codex → any model) | any OpenAI-compatible endpoint (OpenRouter / local / fleet Qwen) |
| Needs | Claude Code (or another loop host) | just Python — no Claude Code |
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

## Path 2 — the `heal` CLI (headless, any model)

`scripts/heal.py` is the out-of-band healer — the engine the overnight job uses,
and usable on demand. **No Claude Code required**; direct call to whatever model
you point it at. (Uses pytest's JUnit XML + sync Playwright under the hood.)

```bash
BASE_URL=<app-url> \
HEAL_BASE_URL=<openai-compatible endpoint> \
HEAL_MODEL=<model id> \
[HEAL_API_KEY=<key>] \
python scripts/heal.py [-k <name>] [--max N] [--open-pr] [--tickets off|annotate|file]
```

Per failing test: run it → reproduce in a real browser → read the **live
accessibility snapshot** → ask `HEAL_MODEL` for a resilient semantic locator →
apply → **re-run to verify**. Locators only; an unhealable failure is reverted and
flagged for a human. `--open-pr` assembles one PR with the decisions.

**Model examples:**
```bash
# Fleet Qwen3.8-27B via its attributed proxy
HEAL_BASE_URL=http://192.168.1.47:3025/v1 HEAL_MODEL='ollama@localhost/qwen3.8-27b:latest' python scripts/heal.py

# OpenRouter
HEAL_BASE_URL=https://openrouter.ai/api/v1 HEAL_MODEL='...' HEAL_API_KEY=sk-or-... python scripts/heal.py
```

**Flags:** `-k <name>` (pytest keyword scope), `--max N`, `--open-pr`,
`--tickets off|annotate|file` (suspected app-bugs → annotate surfaces a matching
open ticket; file creates deduped ones; `TICKET_TARGETS=clickup,jira` selects
systems, needs their creds in env).

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
   point at a **local/cheap model** (e.g. local Ollama), so keeping tests green
   never burns your agent budget.

Conventions either way: one feature per test module, pytest markers, resilient
semantic locators, data-agnostic assertions, and page objects for anything reused.

## Which path?
- **Authoring new tests / interactive triage** → Path 1 (Claude Code + agents).
- **CI, nightly, unattended, swap models freely** → Path 2 (the `heal` CLI).

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
| Console | verbose, short tracebacks |

Allure output (`test_artifacts/allure/`) continues as before. Override any
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
