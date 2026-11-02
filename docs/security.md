# Security and privacy plan

This document describes safeguards to build and verify. The application is not implemented or security-reviewed yet. The initial target is a single user running it on their own computer; it is not ready for untrusted users or public internet deployment.

## Private data and credentials

- Each user chooses a provider and enters their own API key in a password field. Plan to keep the key only in the current browser tab and in server request memory, with no storage by default in files, cookies, browser storage, logs, telemetry, or Git. Environment variables are for developer or integration tests, not a shared production key. Ignore local secret files such as `.env`; an example file must contain placeholders only.
- Send a key only in a request body or authorization header to the local backend, then to the selected provider's fixed, allowlisted HTTPS endpoint. Never put it in a URL or send it to a job-posting site. Validate provider selection, enforce TLS verification, and prevent redirects from carrying credentials to another host.
- Ask for user consent before sending resume content and job details to an AI provider. Show which provider receives the data and that its API may charge for use. Use synthetic text for connection checks.
- Keep uploads, extracted text, drafts, and exports in memory where practical. If temporary files are necessary, use a private directory, restrictive permissions, and cleanup on completion and failure; document that interruptions can leave files behind. Do not log resumes, job descriptions, provider responses, keys, or sensitive URL query strings. File deletion is not a promise of secure erasure.
- Provider privacy and retention terms differ. OpenAI states that API data is not used for model training by default unless the customer opts in; its default abuse-monitoring logs may retain content for up to 30 days, with exceptions. Setting `store: false` alone is not a zero-retention guarantee. Google's unpaid-service terms may permit using submitted content to improve products and warn against submitting personal information where those terms apply. Show the selected provider and its relevant plan-specific notice before sending a resume. Check the current [OpenAI data controls](https://developers.openai.com/api/docs/guides/your-data), [Gemini terms](https://ai.google.dev/gemini-api/terms), and [Claude API data retention](https://platform.claude.com/docs/en/manage-claude/api-and-data-retention) before making privacy claims.

## Untrusted inputs

**Resumes.** Accept only the planned PDF and DOCX formats. Validate file signatures as well as extensions; set upload, page, archive-entry, decompressed-size, and processing-time limits. Reject malformed or encrypted files that cannot be safely processed, and never execute document macros, scripts, or embedded content. Parse files in a resource-limited worker where the operating system permits it. A scanned PDF needs a clear text-entry fallback rather than pretending it was extracted. These controls follow [OWASP's file-upload guidance](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html).

**Job URLs.** A URL importer can otherwise reach a user's local network or cloud metadata service. Permit only HTTP or HTTPS URLs without embedded credentials, reject non-public IPv4 and IPv6 destinations, disable implicit environment proxies, and bind each connection to a validated address while preserving the original hostname for the Host header, TLS SNI, and certificate verification. A separate DNS check followed by an unchecked lookup is not sufficient. Disable redirects initially or validate and pin every redirect and retry. Limit ports, redirect count, time, and compressed and decompressed response size; never load page subresources. Provide pasted text as a fallback. See [OWASP's SSRF guidance](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html) and the [HTTPX SNI extension](https://www.python-httpx.org/advanced/extensions/).

**AI output.** Treat resumes, job descriptions, and model responses as untrusted data, not instructions. Give the model no browser, network, or file tools. Validate output against a strict schema and link proposed claims to candidate-provided evidence. A schema, prompt, or evidence link cannot prove semantic accuracy: show the changes and ask the user to review them. Do not insert skills, dates, credentials, or achievements missing from the source unless the user explicitly confirms them as true. Test adversarial instructions and fabricated claims, following [OWASP's prompt-injection guidance](https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html).

## Local access and exports

Bind the local server to loopback, validate allowed hosts and origins, and protect state-changing requests against cross-site requests. Use a restrictive content security policy, escape untrusted text, and avoid broad CORS permissions. Never send credentials back in responses or expose them to other browser tabs or origins. Bound request sizes and concurrent work, and return useful errors without sensitive internals.

Generate downloads only when requested. Verify that exported PDF and DOCX files retain the reviewed content and reading order, render correctly, and do not include unwanted document metadata or hidden content. Users should review the final output before using it.

## Before any public deployment

Add authentication and per-user authorization, tenant isolation, HTTPS, abuse and spending controls, protected secrets, explicit retention and deletion policies, restricted outbound networking, and operational monitoring. Run end-to-end security tests and an independent review before describing a hosted deployment as production-ready.

## Reporting concerns

Never include a real resume, API key, or other sensitive data in a public issue. If GitHub private vulnerability reporting is available, use it; otherwise ask the maintainers for a private reporting channel before sharing details.
