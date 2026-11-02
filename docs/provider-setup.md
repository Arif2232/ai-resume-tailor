# Provider connection checks

Each app user chooses a provider and supplies their own API key. The app does not need a shared provider key. Check the chosen provider's pricing and privacy terms before sending a real resume.

The checks below send only synthetic text, use hidden key input when no environment variable is set, and may incur API charges. They do not save or print the key. Run them in the project folder after installing the dependencies described in the [README](../README.md).

## OpenAI

Install the optional `openai-check` dependencies first, as shown in the [OpenAI setup guide](openai-setup.md).

```sh
.venv/bin/python scripts/verify_openai.py
```

The default is `gpt-6.1-terra`. See the [OpenAI setup guide](openai-setup.md) for billing, optional environment variables, and Windows commands.

## Gemini or Claude

```sh
.venv/bin/python scripts/verify_provider.py gemini
.venv/bin/python scripts/verify_provider.py claude
```

On Windows, replace `.venv/bin/python` with `.venv\Scripts\python.exe`. The default models are `gemini-3.8-flash` and `claude-sonnet-5-5`. The scripts may also use `GEMINI_API_KEY` or `ANTHROPIC_API_KEY` from the current process environment, and optional `GEMINI_MODEL` or `ANTHROPIC_MODEL` overrides. They do not load `.env` files.

If a Claude key can access multiple workspaces, the browser offers an optional workspace ID; the command-line check accepts it in `ANTHROPIC_WORKSPACE_ID`.

The app also offers an optional connection test in the browser. A successful test verifies only the selected key, model, and a small structured response; it does not establish resume quality or prove every provider feature works. Claude's integration has only been tested with mocked responses so far.

Review [OpenAI data controls](https://developers.openai.com/api/docs/guides/your-data), [Gemini terms](https://ai.google.dev/gemini-api/terms), and [Claude data retention](https://platform.claude.com/docs/en/manage-claude/api-and-data-retention). Gemini's free-tier terms may allow submitted content to be used to improve products.
