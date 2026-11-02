# AI Resume Tailor

**Your experience, tailored to the opportunity.**

Upload your resume, add a job description, and review an AI-assisted draft with explanations and source evidence. Export the result as a simple PDF or Word document, or copy the text.

> **Early local version.** The core workflow and offline tests are implemented. A user reported a successful synthetic tailoring run with OpenAI and a successful Gemini connection check. Broader live evaluation remains; Claude is experimental and has not been live-verified. This app is not ready to be exposed to the public internet.

## What it does

- Reads text-based PDF and DOCX resumes and lets you correct the extracted text.
- Accepts a pasted job description or imports text from a public job link.
- Lets you choose OpenAI, Gemini, or Claude and enter your own API key.
- Shows an editable draft, original-to-revised changes, job alignment, and source quotes.
- Keeps missing skills as suggestions. They are added only when you confirm you have them.
- Exports a single-column PDF or Word file, or copies the reviewed text.

AI can make mistakes or omit details. Review every claim, date, and skill before using the output. Source quotes and format checks help, but they do not prove factual accuracy or guarantee an ATS or AI-detector outcome.

## Get started

You need **Python 3.11 or newer**, an internet connection, and an API key from your chosen provider. The app runs on your computer; it sends resume and job text to the provider only after you choose to generate a draft. Provider terms and API charges apply.

1. On this repository page, select **Code → Download ZIP** and unzip the folder, or clone it with Git.
2. Open a terminal in the extracted folder. Install Python from [python.org](https://www.python.org/downloads/) if needed; on Windows, select **Add Python to PATH** during installation.
3. Run the commands for your computer below. The first install downloads the app's dependencies.

**macOS or Linux**

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m resume_tailor
```

**Windows PowerShell**

```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -e .
.venv\Scripts\python.exe -m resume_tailor
```

4. The app opens in your browser. Keep the terminal open. If it does not open automatically, use the local address printed in the terminal.
5. Select **AI settings**, choose a provider and model, enter your API key, and select **Test connection**. Once it succeeds, create a settings password and select **Save and continue**. To keep the key only until the tab closes, uncheck the encrypted-save option instead.
6. Upload a resume or paste its text, add a job description or link, review the data-sharing notice, and select **Tailor my resume**.
7. Check the draft and its evidence. Add only suggestions you actually have, edit as needed, and confirm the details before copying or downloading.
8. Press **Ctrl+C** in the terminal to stop the app.

When you reopen the app, open **AI settings** and use your password to **Unlock and test** the saved connection. You can also change it or forget it there. The password cannot be recovered. Testing is required before tailoring; it sends a small synthetic request, may incur a charge, and does not send your resume. See the [provider setup guide](docs/provider-setup.md) for independent checks.

## Limits and privacy

- If you choose to save your connection, the browser encrypts your API key with your settings password before storing it in a local settings file. The password is not saved or sent to the server. The app does not use an operating-system keychain. A strong, unique password helps protect the saved key; software with access to your browser while the key is unlocked may still see it.
- Your resume and job text stay on your computer until you choose to send them to the selected AI provider. Provider retention and training terms differ. Gemini's free-tier terms may allow content to be used to improve products; check your plan before sending personal information.
- Scanned/image-only PDFs need a text version. Complex PDF layouts and Word features such as tracked changes may not extract perfectly; review the extracted text.
- Job sites that require sign-in, use scripts to display content, or block automated access may not import. Paste the description instead.
- PDF export currently supports common left-to-right scripts with the bundled font. If characters cannot be rendered safely, use the Word export. Review both the content and final layout.
- The local service has no multi-user authentication. Do not expose it directly to the internet; see the [deployment plan](docs/deployment.md).

## Development

On macOS or Linux, install the development tools and run the offline tests:

```sh
.venv/bin/python -m pip install -e '.[dev,openai-check]'
.venv/bin/python -m playwright install chromium
.venv/bin/python -m pytest -q
```

On Windows, use `.venv\Scripts\python.exe` in place of `.venv/bin/python`. Tests use synthetic resumes and mocked AI responses; they do not verify a real provider key or model quality. The bundled DejaVu fonts have their own [license](src/resume_tailor/assets/fonts/LICENSE-DejaVu.txt).

See the [architecture](docs/architecture.md), [security plan](docs/security.md), [contribution guide](CONTRIBUTING.md), and [MIT license](LICENSE).
