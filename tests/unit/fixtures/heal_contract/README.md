# Heal contract fixtures (a copy)

Golden request, script and expected-answer files copied from the heal service repository (`fixtures/contract/`). Each case
is one drifted page object and one scripted conversation with the service; `expected.json` records what the service answered at
each step. `tests/unit/test_heal_contract.py` replays every case through `utils/heal_client.py` against a fake service that
answers from `expected.json`, and checks that the client checks the same locator live, reports what it saw, writes the same
locator into the file (or leaves the file alone) and ends with the same decision. The TypeScript client replays the same files.

Refresh by copying the service repository's `fixtures/contract/` over this folder (the case files are deterministic). Examples
use `localhost` and `app.example` only; `test_the_fixtures_hold_no_internal_host_or_address` checks that.
