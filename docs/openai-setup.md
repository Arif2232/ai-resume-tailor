# Stage 2: check OpenAI

This is a developer connection check, separate from the resume application. Each app user selects a provider and enters their own key. A user reported successful synthetic OpenAI and Gemini connection checks; Claude has not been live-verified.

## What you need

- Python 3.11 or newer.
- An [OpenAI API account and project API key](https://platform.openai.com/api-keys), with access to `gpt-6.1-terra` and any required API billing or credits. Some eligible ChatGPT subscriptions can [claim API credits](https://developers.openai.com/api/docs/guides/chatgpt-api-credits); check your account's current settings.
- An internet connection. This check sends a small synthetic request to OpenAI, **not a resume**, and may incur an API charge. See [pricing](https://developers.openai.com/api/docs/pricing) and [data controls](https://developers.openai.com/api/docs/guides/your-data).

## Run the check

Open a terminal in the project folder. On macOS or Linux:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[openai-check,dev]'
.venv/bin/python scripts/verify_openai.py
```

On Windows, in PowerShell:

```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -e '.[openai-check,dev]'
.venv\Scripts\python.exe scripts\verify_openai.py
```

If `OPENAI_API_KEY` is not already set in the terminal's environment, the script asks for the key with hidden input. Paste it **only after that prompt appears**, then press Enter. Do not put it in chat, a command, or a committed file. The script does not save it. If the environment variable is already set, it uses that value without prompting. The `.env.example` file is only a placeholder; the script does not load `.env` files.

The check defaults to `gpt-6.1-terra`; a developer may set `OPENAI_MODEL` in the environment to test another supported model. Success prints `Connected. OpenAI returned the expected structured response.` A failure reports a general reason without printing the key. Check model access, API billing, rate limits, or connectivity as indicated.

For safety, the check refuses to run if `OPENAI_CUSTOM_HEADERS` is set. Unset it in that terminal before trying again; custom headers could otherwise change the credentials used by the SDK.

For automated offline tests on macOS or Linux, run:

```sh
.venv/bin/python -m pytest -q tests/test_verify_openai.py tests/test_verify_provider.py
```

On Windows, use `.venv\Scripts\python.exe -m pytest -q tests/test_verify_openai.py tests/test_verify_provider.py`.

Those tests use fake credentials and mocked responses. A passing offline suite does not verify a real API key, model access, billing, or the full tailoring workflow.
