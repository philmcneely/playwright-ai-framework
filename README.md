
# 🎭 Playwright AI Test Framework - The Internet Test Site

This guide explains how to set up and run Playwright-based Python tests with Allure reporting on **macOS**, **Windows**, and **Linux**.

---

## Prerequisites

**All Platforms:**
- [Python 3.11+](https://www.python.org/downloads/)
- [pip](https://pip.pypa.io/en/stable/installation/)
- [Node.js](https://nodejs.org/) (for Playwright browser installation)
- [Allure Commandline](https://docs.qameta.io/allure/#_installing_a_commandline)
- [`python-dotenv`](https://pypi.org/project/python-dotenv/) (for loading `.env` files)

**Windows Only:**
- [Visual C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/)

**macOS Only:**
- [Homebrew](https://brew.sh/) (recommended for installing Allure and Node.js)

---

## 1. Clone the Repository

```sh
git clone https://github.com/your-org/your-repo.git
cd your-repo
```

---

## 2. Create Environment Files

Create the environment file(s) you need in the project root:

- `.env.dev` for development
- `.env.test` for test
- `.env.prod` for production

Each file should contain the environment variables your tests require, for example:

```
BASE_URL=https://your-base-url
API_LOGIN_URL=https://your-api-url
USER_EMAIL=pm@example.com
USER_PASSWORD=yourpassword
# ...and so on for all required variables
```
Alternately, these files should be available in your secrets server and may need to be customized for your tests.

---

## 3. Set Up a Python Virtual Environment

**macOS/Linux:**

```sh
python3 -m venv .venv
source .venv/bin/activate
```

**Windows (Command Prompt):**

```cmd
python -m venv .venv
.venv\Scripts\activate
```

**Windows (PowerShell):**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

---

## 4. Install Python Dependencies

```sh
pip install --upgrade pip
pip install -r requirements_with_versions.txt
```

Make sure your `requirements_with_versions.txt` includes:

```
python-dotenv
opencv-python
pillow
numpy
```

---

## 5. Install Playwright Browsers

**Important:** This step is required to download browser binaries for Chromium, Firefox, and WebKit.

```sh
python -m playwright install --with-deps
```

> **Note:** If you encounter "Executable doesn't exist" errors when running tests with specific browsers (e.g., Firefox), make sure you've run this command to install all browser binaries.

---

## 6. Install Allure Commandline

**macOS (with Homebrew):**

```sh
brew install allure
```

**Linux:**

```sh
sudo apt-get install default-jre
wget https://github.com/allure-framework/allure2/releases/download/2.27.0/allure-2.27.0.tgz
tar -xzf allure-2.27.0.tgz
sudo mv allure-2.27.0 /opt/allure
sudo ln -s /opt/allure/bin/allure /usr/bin/allure
```

**Windows:**

- Download the [Allure zip](https://github.com/allure-framework/allure2/releases) and extract it.
- Add the `bin` folder to your `PATH` environment variable.
- Open a new terminal and run `allure --version` to verify.

---

## 7. Load Environment Variables Automatically

Add this to your `conftest.py` or at the top of your test entrypoint:

```python
import os
from dotenv import load_dotenv

# Choose the environment file you want to load
env_file = os.getenv("ENV_FILE", ".env.dev")
load_dotenv(dotenv_path=env_file)
```

You can set the `ENV_FILE` environment variable to switch between `.env.dev`, `.env.test`, or `.env.prod`.

**Example:**

```sh
ENV_FILE=.env.test pytest ...
```

---

## 8. Run the Tests

Run your tests with pytest. For example, to run smoke tests with Allure reporting, reruns and in parallel:

```sh
pytest --alluredir=test_artifacts/allure/allure-results --capture=tee-sys --reruns 2 --reruns-delay 5 -m smoke -n auto
```

- Adjust the `-m smoke` marker or other pytest options as needed.

You can also pass env vars on the commandline, for example if you want headed tests or a different browser.

```sh
BROWSER=firefox HEADLESS=false pytest --alluredir=test_artifacts/allure/allure-results --capture=tee-sys --reruns 2 --reruns-delay 5 -m smoke -n auto
```

Adjust as needed.

---

## 9. Generate the Allure Report

```sh
allure generate test_artifacts/allure/allure-results -o test_artifacts/allure/allure-report --clean --single-file
```

---

## 10. View the Allure Report

**macOS:**

```sh
open test_artifacts/allure/allure-report/index.html
```

**Linux:**

```sh
xdg-open test_artifacts/allure/allure-report/index.html
```

**Windows:**

Open `test_artifacts\allure\allure-report\index.html` in your browser.

---

## 11. Github Actions

Everything is already configured to run a smoke test, then if that passes it will run the full 'login' test suite. All secrets are configured on the repo level, so if you add any, you will need to update the config.

---

## 12. Visual Regression Testing

- Baselines managed in `test_artifacts/visual/visual_baselines/`
- Current run in `test_artifacts/visual/visual_current/`
- Diffs (with OpenCV highlights) in `test_artifacts/visual/visual_diffs/`

Example:

```python
@pytest.mark.asyncio
async def test_homepage_visual(page, visual_regression):
    await page.goto("https://example.com")
    await visual_regression("homepage", tolerance=0.02)
```

Run:

```sh
pytest tests/visual_regression/ -v
```

---

## 13. API Mocking

- Mock GET/POST/PUT/DELETE
- Load from files
- Handle slow responses

Example:

```python
await api_mocker.mock_get("**/api/users", {"users": [{"id": 1}]})
```

---

## 14. AI Self-Healing

The Ollama Python library is installed as part of `requirements_with_versions.txt`.

# Ollama Model Setup for AI Healing

**Check Available Models**

```sh
ollama list
```

**Pull a Suitable Model**

### For vision + text analysis (recommended for screenshot analysis):

```sh
ollama pull llava:7b
# or
ollama pull llava:13b
```

### For text-only analysis (faster, smaller):

```sh
ollama pull llama3.1:8b
# or
ollama pull llama3.2:3b
```

**Update Your Environment Variable**

Set the model you actually have:

```sh
export OLLAMA_MODEL=llava:7b
# or whatever model you pulled
```

**Test Ollama is Working**

```sh
ollama run llava:7b "Hello, can you analyze test failures?"
```

This is not configured on Github Actions due to needing a larger machine runner.
Reports will be found in test_artifacts/ai/ai_healing_reports

To see this in action, you can run a test specifically created to show it in action by running
```sh
AI_HEALING_ENABLED=true ENV=dev SKIP_SCREENSHOTS=0 HEADLESS=false pytest --alluredir=test_artifacts/allure/allure-results --capture=tee-sys --reruns 2 --reruns-delay 5 -m trigger_ai_healing
```

This is an example of commandline output

```sh
🧠 Test failed, capturing context for AI healing: test_login_direct_valid_credentials
Screenshot saved and attached to Allure: screenshots/tests_login_test_login.py_test_login_direct_valid_credentials_2025-07-29_21-37-36.png
💾 Context saved for AI healing hook (key: tests/login/test_login.py::test_login_direct_valid_credentials)

🧠 Final failure detected for test_login_direct_valid_credentials, triggering AI healing
🤖 Using Ollama at http://localhost:11434 with model gemma2:2b
🤖 Checking Ollama service at http://localhost:11434...
🤖 Ollama executable path: /usr/local/bin/ollama
🤖 Ollama service is already running.
🤖 Checking if model gemma2:2b is available...
🤖 Warming up model gemma2:2b (waiting for a real response)...
🤖 Model gemma2:2b is loaded and ready.
🧠 Calling Ollama for AI healing analysis...
🧠 Querying Ollama model: gemma2:2b
📸 Including screenshot: screenshots/tests_login_test_login.py_test_login_direct_valid_credentials_2025-07-29_21-37-36.png
🤖 Raw Ollama response (first 200 chars): ```json
{
    "analysis": "The error message 'LoginPage' object has no attribute 'enter_passwordx' indicates that the code is trying to access an element named 'enter_passwordx' which doesn't exist wi...
🤖 Found JSON in code block
✅ Successfully parsed JSON response
🤖 Full Ollama response: {'analysis': "The error message 'LoginPage' object has no attribute 'enter_passwordx' indicates that the code is trying to access an element named 'enter_passwordx' which doesn't exist within the LoginPage class. This likely means there's a typo in the test code, or the element name might have been changed.", 'root_cause': 'Typographical error in the test code (e.g., incorrect element name)', 'confidence': 0.95, 'suggested_fix': 'Verify the element names used in the test code against the actual HTML structure of the LoginPage class. Double-check for typos or misspellings.', 'updated_test_code': "```python\n@pytest.mark.login\nasync def test_login_direct_valid_credentials(app):\n    # ... (rest of the code)\n    await app.login_page.enter_passwordx(PERSONAS['user']['password']) \n    # ... (rest of the code)\n```", 'recommendations': "It's recommended to use a robust test framework like pytest for better test organization and error handling.  Consider using assertions to ensure that elements are found correctly, and implement strategies to handle flaky tests effectively.", 'raw_ollama_response': '```json\n{\n    "analysis": "The error message \'LoginPage\' object has no attribute \'enter_passwordx\' indicates that the code is trying to access an element named \'enter_passwordx\' which doesn\'t exist within the LoginPage class. This likely means there\'s a typo in the test code, or the element name might have been changed.",\n    "root_cause": "Typographical error in the test code (e.g., incorrect element name)",\n    "confidence": 0.95,\n    "suggested_fix": "Verify the element names used in the test code against the actual HTML structure of the LoginPage class. Double-check for typos or misspellings.",\n    "updated_test_code": "```python\\n@pytest.mark.login\\nasync def test_login_direct_valid_credentials(app):\\n    # ... (rest of the code)\\n    await app.login_page.enter_passwordx(PERSONAS[\'user\'][\'password\']) \\n    # ... (rest of the code)\\n```",\n    "recommendations": "It\'s recommended to use a robust test framework like pytest for better test organization and error handling.  Consider using assertions to ensure that elements are found correctly, and implement strategies to handle flaky tests effectively." \n}\n```'}
🧠 AI analysis complete, generating healing report...
💾 Ollama healed test saved: ai_healing_reports/test_login_direct_valid_credentials_20250729_213826_ollama_healed.py
```

You can see some example reports and attempts at fixing the files in `test_artifacts/ai/ai_healing_reports/`


## 15. BrowserStack Integration

You can run your Playwright tests on real browsers in the cloud using [BrowserStack](https://www.browserstack.com/). This is useful for cross-browser and cross-OS testing without maintaining your own infrastructure.

### 1. Prerequisites

- You must have a [BrowserStack account](https://www.browserstack.com/users/sign_up).
- Your account's **Username** and **Access Key** (found in your BrowserStack dashboard).

### 2. Install Required Python Package

Install the BrowserStack Local Python bindings:

```sh
pip install browserstack-local
```

### 3. Set BrowserStack Credentials

Add the following to your `.env.dev` (or relevant `.env` file):

```
BROWSERSTACK_USERNAME=your_browserstack_username
BROWSERSTACK_ACCESS_KEY=your_browserstack_access_key
BROWSERSTACK_ENABLED=true
```

> **Note:** Set `BROWSERSTACK_ENABLED=false` to run tests locally.

### 4. How It Works

When `BROWSERSTACK_ENABLED=true`, the test runner will:
- Connect to BrowserStack using your credentials.
- Launch the specified browser/OS in the cloud.
- Run your Playwright tests remotely.

When `BROWSERSTACK_ENABLED=false`, tests run locally as usual.

### 5. Running Tests on BrowserStack

Activate your virtual environment and run:

```sh
BROWSERSTACK_ENABLED=true pytest --alluredir=test_artifacts/allure/allure-results
```

You can also set the environment variable in your `.env.dev` file.

### 6. Customizing Browser/OS

Edit the capabilities in the `conftest.py` file under the `caps` dictionary to change browser, version, OS, etc. Example:

```python
caps = {
    "browser": "chrome",
    "browser_version": "latest",
    "os": "osx",
    "os_version": "sonoma",
    "name": "Playwright Test",
    "build": "playwright-python-build-1",
    "browserstack.username": os.getenv("BROWSERSTACK_USERNAME"),
    "browserstack.accessKey": os.getenv("BROWSERSTACK_ACCESS_KEY"),
}
```

See [BrowserStack Playwright Capabilities](https://www.browserstack.com/docs/automate/playwright/python#capabilities) for more options.

### 7. Viewing Results

- Test results and screenshots will be available in your BrowserStack dashboard.
- Allure reports will still be generated locally if you use `--alluredir`.

---

**Tip:**  
You can switch between local and BrowserStack runs by toggling the `BROWSERSTACK_ENABLED` variable, without changing your test code.

---

## 16. Jira Integration

Automatically post test results to Jira tickets and trigger workflow transitions on pass/fail. Conditionally enabled via environment variables.

### Setup

Add the following to your `.env.dev` (or relevant `.env` file):

```
JIRA_ENABLED=true
JIRA_BASE=https://your-instance.atlassian.net
JIRA_USER=you@example.com
JIRA_TOKEN=your_api_token
JIRA_DRY_RUN=false
```

> **Note:** Set `JIRA_ENABLED=false` to disable Jira reporting entirely. Set `JIRA_DRY_RUN=true` to log what would be posted without making actual API calls.

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `JIRA_ENABLED` | `false` | Enable/disable Jira reporting |
| `JIRA_BASE` | — | Jira instance URL |
| `JIRA_USER` | — | Jira username/email |
| `JIRA_TOKEN` | — | Jira API token |
| `JIRA_JQL` | `project = ABC AND status in ("To Do", "In Progress")` | JQL filter for ticket lookup |
| `JIRA_DRY_RUN` | `false` | Log instead of posting |
| `JIRA_TRANSITION_ON_PASS` | — | Workflow transition name when test passes |
| `JIRA_TRANSITION_ON_FAIL` | — | Workflow transition name when test fails |

### How It Works

1. Test names or node IDs are scanned for Jira ticket patterns (e.g., `PROJ-123`).
2. On test completion (pass or final retry failure), a formatted comment is posted to the ticket.
3. If transition env vars are configured, the ticket's workflow state is updated automatically.

### Linking Tests to Tickets

Include the ticket ID in your test name or file path:

```python
def test_PROJ_123_login_flow(page):
    ...
```

Or use pytest marks/node IDs that contain the ticket pattern `[A-Z][A-Z0-9]+-\d+`.

---

## 17. Test Observability

Structured per-test metrics collection with JSONL output, summary reports, and error categorization. Tracks flake rate, pass rate, slowest tests, heal events, and failures by category.

### Setup

```
OBSERVABILITY_ENABLED=true
```

> **Note:** Set `OBSERVABILITY_ENABLED=false` to disable metric collection entirely. Zero overhead when disabled.

### What Gets Tracked

Each test execution records:

| Field | Description |
|---|---|
| `test_id` | Unique test identifier (node ID) |
| `test_name` | Human-readable test name |
| `suite` | Test suite/module |
| `status` | passed, failed, skipped |
| `duration_ms` | Execution time in milliseconds |
| `retry_count` | Number of retries for this test |
| `browser` | Browser engine used |
| `commit_sha` | Git commit (auto-detected) |
| `branch` | Git branch (auto-detected) |
| `heal_event` | Whether AI healing was triggered |
| `error_category` | Auto-categorized: timeout, element-not-found, navigation, assertion, browser-crash, other |

### Output Files

| File | Location |
|---|---|
| JSONL metrics | `test_artifacts/observability/metrics.jsonl` |
| Summary JSON | `test_artifacts/observability/summary.json` |
| Markdown report | `test_artifacts/observability/report.md` |

### Running with Observability

```sh
OBSERVABILITY_ENABLED=true pytest --alluredir=test_artifacts/allure/allure-results --capture=tee-sys --reruns 2 --reruns-delay 5 -m smoke -n auto
```

The summary is printed to the console at the end of the session and a Markdown report is written to `test_artifacts/observability/report.md`.

---

**Regenerate Docs for LLMs:**  
This project makes use of OneFileLLM: https://github.com/jimmc414/onefilellm

To install:
```bash
git clone https://github.com/jimmc414/onefilellm.git
cd onefilellm
pip install -r requirements.txt
pip install -e .
```

For GitHub API access (recommended):
```bash
export GITHUB_TOKEN="your_personal_access_token"
```

To regenerate output.xml:
```python
python onefilellm.py https://github.com/philmcneely/playwright-ai-framework
```

You can also run the script against a local repository by providing the local path instead of a GitHub URL, for example:
```python
python onefilellm.py /path/to/your/local/repo
```

---


## Troubleshooting

- **Missing .env file:**  
  Make sure you have created the correct `.env.<env>` file with all required variables.
- **Virtual environment activation issues:**  
  Double-check the activation command for your OS and shell.
- **Allure not found:**  
  Ensure Allure is installed and available in your `PATH`.
- **Windows build errors:**  
  Install the Visual C++ Build Tools as described above.
- **Browser "Executable doesn't exist" errors:**  
  Run `python -m playwright install --with-deps` to download all browser binaries.

---

## Directory Structure 📂

```text
.
├── 📄 .env.dev, .env.test, .env.prod   — Environment variable files
├── 📄 conftest.py                      — Config & fixtures
├── 📄 pytest.ini                       — Pytest settings
├── 📄 requirements_with_versions.txt   — Python deps
│
├── 📂 test_artifacts/                  — Test artifacts
│   ├── 📂 visual/
│   │   ├── 📂 visual_baselines         — Baseline screenshots (committed)
│   │   ├── 📂 visual_current           — Current screenshots (gitignored)
│   │   ├── 📂 visual_diffs             — Diff images (gitignored)
│   ├── 📂 ai/
│   │   └── 📂 ai_healing_reports       — AI healing reports (with committed examples)
│   ├── 📂 allure/                      — Allure reports/results/screenshots (gitignored)
│   ├── 📂 observability/
│   │   ├── 📄 metrics.jsonl            — Per-test JSONL metrics
│   │   ├── 📄 summary.json             — Aggregated summary
│   │   └── 📄 report.md                — Markdown report
├── 📂 pages/                           — Page Object Models
├── 📂 utils/                           — Utilities
│   ├── 📄 visual_regression.py
│   ├── 📄 network_mocking.py
│   ├── 📄 jira_client.py              — Jira REST API client
│   └── 📄 test_observability.py       — Test metrics collector
├── 📂 data/                            — Test data
├── 📂 config/                          — Settings
├── 📂 tests/                           — Test files
│   ├── 📂 login/                       — Login functional/security tests
│   ├── 📂 visual_regression/           — Visual regression tests
│   ├── 📂 api/                         — API mocking tests
│   └── 📂 unit/                        — Framework utility unit tests
```

---

**Happy testing! 🚀**
