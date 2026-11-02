# Security and privacy

The current application is for a single user on their own computer. It has not had an independent security review and is not ready for public internet deployment.

## Credentials and private data

- Users select a provider and enter their own key. The app holds the key in the browser tab and request memory; it does not intentionally save it to files, cookies, browser storage, logs, telemetry, or Git. Developer environment variables are optional and are not a shared app key.
- Provider requests go to fixed HTTPS endpoints with TLS verification, no automatic redirects, and environment proxies disabled. Keys are sent in headers, never in job URLs. Provider error messages are sanitized.
- Resume and job text are sent to the chosen provider only after the user confirms. The optional connection test uses synthetic text. Both may incur charges; the selected provider's terms apply.
- Uploads, extracted text, drafts, and generated exports are processed in memory by the app. Browser downloads are saved where the user chooses. This is not a promise of secure erasure from operating-system memory, swap, browser extensions, backups, or provider systems.
- Provider retention and training terms differ. `store: false` is not a zero-retention guarantee. Check [OpenAI data controls](https://developers.openai.com/api/docs/guides/your-data), [Gemini terms](https://ai.google.dev/gemini-api/terms), and [Claude retention](https://platform.claude.com/docs/en/manage-claude/api-and-data-retention). Gemini's free tier may use submitted content to improve products.

## Untrusted input and output

**Resumes:** The app accepts PDF and DOCX files up to 5 MB. It checks file signatures, limits PDFs to 12 pages, and rejects locked PDFs, DOCX macros, unsafe archive entries, excessive archive expansion, and unreadable text. Parsing runs in a separate process with a timeout; CPU limits are used where available and an address-space limit is applied on Linux. The worker does not inherit provider keys. These controls reduce risk but are not a complete operating-system sandbox on every platform. See [OWASP file-upload guidance](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html).

**Job URLs:** Only public HTTP/HTTPS destinations on standard ports are accepted. DNS answers are checked and the connection is pinned to a validated address while preserving the original Host and TLS name. Redirects are revalidated, environment proxies are disabled, and response size and time are bounded. Compressed responses are rejected. A paste fallback is available. These controls do not replace network-level egress restrictions for a hosted deployment. See [OWASP SSRF guidance](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html).

**AI output:** Resume and job text are treated as untrusted data. The provider receives no app tools. The app validates the structured response, checks source quotes and some changed numbers, and keeps suggested skills separate until the user confirms them. These checks do not prove semantic accuracy or detect every invented claim. The user must review the draft and confirm its accuracy before export. See [OWASP prompt-injection guidance](https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html).

## Local access and exports

The app binds to loopback, checks the Host and a per-process request token, restricts browser content sources, and does not enable broad CORS. Requests and concurrent work are bounded. PDF and DOCX exports are generated from reviewed text; users should inspect their content and layout before use.

The PDF renderer currently rejects characters it cannot safely render and offers Word as a fallback. Document extraction may omit content from complex layouts or tracked changes. Browser and operating-system behavior can vary; Windows and Linux have not yet been tested interactively.

## Reporting and deployment

Never include a real resume, API key, or other sensitive data in a public issue. The repository has private vulnerability reporting enabled; use [SECURITY.md](../SECURITY.md). See the [deployment plan](deployment.md) for authentication, isolation, egress, retention, monitoring, and independent review required before hosting.
