# Architecture

This describes the current local implementation and the work still needed before a stable or hosted release. A user reported a successful synthetic OpenAI tailoring run; the full workflow has not been live-evaluated across providers.

## Product flow

1. The user uploads a PDF or Word resume, or pastes its text. Extraction runs in a separate bounded worker and the user can correct the result.
2. The user pastes a job description or imports a public job URL. A failed import offers the paste fallback.
3. In AI settings, the user chooses and tests a provider, model, and their own API key. The connection can be saved as an encrypted local file or kept only for the current tab. The user explicitly agrees before sending resume and job text to the provider.
4. The model proposes an editable resume, explains changes and job alignment, and cites source text. Missing skills remain separate suggestions until the user confirms them.
5. The user reviews the result and confirms its accuracy before copying or downloading a PDF or Word file.

The app does not submit job applications. It aims for natural, readable writing and straightforward document structure without promising an ATS result or AI-detector outcome.

## Components

- **Local interface:** FastAPI serves an accessible HTML, CSS, and JavaScript interface on loopback. It has no account system or database.
- **Document input:** [pypdf](https://pypdf.readthedocs.io/en/stable/user/extract-text.html) reads text-based PDFs and [python-docx](https://python-docx.readthedocs.io/en/stable/) reads Word files. A worker, size limits, and timeouts reduce exposure to malformed files. Extraction can still miss content in complex layouts or tracked changes.
- **Job import:** HTTPX fetches public pages with DNS validation and pinned addresses; Beautiful Soup extracts readable text. See [security](security.md) for limits and deployment caveats.
- **AI providers:** a small adapter calls fixed OpenAI, Gemini, or Claude endpoints with the user's key. It uses structured output and validates the response. OpenAI and Gemini connection checks were reported successful by a user; Claude is experimental and unverified live.
- **Review and export:** one structured proposal drives the editable text, changes, alignment, and source evidence. [ReportLab](https://docs.reportlab.com/reportlab/userguide/ch3_fonts/) and python-docx generate PDF and Word files from the same reviewed text.

Source references, schema validation, and number checks reduce some errors but cannot establish semantic truth. Users must check all claims before export. User documents are not intentionally persisted by the app; provider keys are persisted only when users choose encrypted saving. Provider data terms and charges still apply.

## Stages and verification

| Stage | Status and exit check |
| --- | --- |
| 1. Plan | Repository, scope, architecture, and security boundaries created. |
| 2. API setup | Synthetic OpenAI and Gemini connection checks reported successful by a user. Claude still needs a live key check. |
| 3. Core | Input, tailoring, explanations, review, copy, PDF, and Word implemented and exercised with synthetic fixtures and mocked AI. A user reported a successful synthetic OpenAI draft; broader live evaluation remains. |
| 4. Hardening | Offline security, error, browser, and document tests exist. More platform testing, load testing, and independent review remain before a production claim. |
| 5. Release | The public repository has setup and contribution documentation. It is an early local release, not a stable hosted deployment; see [deployment](deployment.md). |

Before sending real resumes, review the selected provider's current terms: [OpenAI](https://developers.openai.com/api/docs/guides/your-data), [Gemini](https://ai.google.dev/gemini-api/terms), or [Claude](https://platform.claude.com/docs/en/manage-claude/api-and-data-retention). A `store: false` setting alone is not a promise of zero retention or no training under every plan.
