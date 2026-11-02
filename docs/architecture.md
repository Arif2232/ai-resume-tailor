# Architecture plan

This document describes the proposed first release. The application and its integrations have not been implemented or verified yet.

## Product flow

1. The user uploads a PDF or Word resume and provides a job description as text or a public URL. If a file cannot be read or a URL is inaccessible, the app explains the issue and offers a way to supply text instead.
2. The app extracts the resume and job text, displays it for correction, and identifies relevant requirements. Documents and web pages are treated as untrusted input.
3. The user chooses an AI provider and supplies their own API key. The model proposes a revised resume, identifies the source of each change, and lists possible missing details separately. A suggested skill or experience is not added as fact until the user confirms it is true.
4. The user reviews and edits the result and sees what changed and why. The app offers text copying and downloads as PDF and Word files.

The app helps people describe their real experience. It does not submit job applications. It should write naturally without promising to defeat AI detectors or pass every applicant tracking system (ATS).

## Proposed stack

Use one local-first Python application: FastAPI for HTTP endpoints, Pydantic for validated data, and a small accessible HTML, CSS, and JavaScript interface. Run the server on the user's computer and bind it to loopback by default. This avoids an account system, a database, and a separate frontend build for the first release. It is not a public hosting design; see [security](security.md) for the additional work required before internet deployment.

Use a shared, structured resume representation for extracted facts, experience, skills, and sections. Each proposed claim should point to source material or a user confirmation. Verify that references exist and require review: a valid reference or model-produced schema does **not** prove the wording is factually supported.

Proposed document libraries are [pypdf](https://pypdf.readthedocs.io/en/stable/user/extract-text.html) for text-based PDF input, [python-docx](https://python-docx.readthedocs.io/en/stable/) for Word input and output, and [ReportLab](https://docs.reportlab.com/reportlab/userguide/ch3_fonts/) for PDF output with embedded fonts. Generate both outputs from the same reviewed content. Keep a straightforward reading order and verify it by extracting text from the generated files as well as reviewing their visual layout. PDF extraction can misread columns or formatting; scanned PDFs require a clear fallback rather than an OCR promise. Word extraction also needs checks for tables, headers, footers, and tracked changes.

Use a small provider adapter so each user can choose OpenAI, Gemini, or Claude with their own key. For the first integration, use the [OpenAI Responses API with structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs), with `gpt-6.1-terra` as a proposed configurable starting model. [GPT-6 Luna](https://developers.openai.com/api/docs/models/gpt-6-luna) is a lower-cost candidate to evaluate, not a guaranteed equivalent. Compare quality, latency, and cost on representative, consented examples before choosing production recommendations. Model availability and [pricing](https://developers.openai.com/api/docs/pricing) depend on the account and can change; Gemini and Claude models and integrations also require current documentation and verification before support is claimed.

Users enter their key in a password field. The browser sends it to the local backend for the chosen provider request; both hold it transiently in memory, without logging or persisting it by default. Developer environment variables may be used for integration tests, but the product does not rely on a shared provider key. Provider endpoints are fixed and allowlisted, and job-URL requests never receive credentials. Sending resume and job text to an AI provider is a network transfer and may incur charges. The app is local-first, not offline, and must explain the selected provider's retention terms before a request.

## Stages and verification

| Stage | Work | Exit check |
| --- | --- | --- |
| 1. Plan | Record scope, architecture, security boundaries, and repository structure. | Review the plan; no working product is claimed. |
| 2. API setup | Configure a chosen provider key and model, without putting secrets in Git. | A small synthetic request verifies the chosen model, schema, credentials, and error handling. Do not proceed to core implementation until this succeeds; verify each additional provider before claiming it works. |
| 3. Core | Build input handling, job text processing, tailoring and explanations, review, text copy, and PDF/Word exports incrementally. | Test each component with synthetic or consented examples. Confirm unsupported claims remain separate until explicitly confirmed. |
| 4. Hardening | Exercise malformed files, unreadable scans, hostile URLs, provider failures, privacy, and accessibility. | Run automated tests and visually inspect plus re-extract representative PDF and Word exports. No ATS compatibility or factual accuracy is assumed from formatting alone. |
| 5. Release | Complete setup, contribution, licensing, deployment, and support documentation. | A fresh checkout can follow the documented setup; unresolved deployment requirements are listed. |

Live provider tests use synthetic text and explicit user action so they do not send a real resume or incur unexpected charges. Explain the chosen provider and its data terms before sending a resume. For example, [OpenAI data controls](https://developers.openai.com/api/docs/guides/your-data), [Gemini pricing and data use](https://ai.google.dev/gemini-api/docs/pricing), and [Claude retention](https://platform.claude.com/docs/en/manage-claude/api-and-data-retention) vary by provider and plan; retention or training may apply even when response storage is disabled.
