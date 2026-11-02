# AI Resume Tailor

**Turn your real experience into a resume tailored to a specific job.**

AI Resume Tailor is an open-source project for improving a resume against a job description while keeping the candidate in control of the facts.

> **Status: planning.** The architecture and safety boundaries are documented; the application, provider integrations, and exports are not implemented or verified yet.

## Planned experience

1. Upload an existing PDF or Word resume.
2. Paste a job description or provide a public job URL.
3. Choose an AI provider and enter your own API key.
4. Review the tailored resume, the changes, and suggested details that need your confirmation.
5. Copy the text or download a readable PDF or Word document.

The app will help highlight genuine experience; it will not add unconfirmed skills or qualifications as facts. It will aim for natural writing and straightforward ATS-readable formatting, but cannot promise an outcome from any ATS or AI detector.

## Proposed approach

The first release is planned as a local-first Python application with FastAPI, a small accessible web interface, and one shared resume model for PDF and Word output. Users will choose their provider and supply their own key; no shared provider key is required. OpenAI, Gemini, and Claude are planned, with OpenAI selected for the first integration check.

The app will need an internet connection to access the chosen provider and optional job URLs. A resume sent to a provider is subject to that provider's terms and may incur charges. See the [architecture plan](docs/architecture.md) and [security plan](docs/security.md) for the boundaries and verification work.

## Project stages

- **1. Planning and repository setup:** document the design and create the project structure.
- **2. API setup:** configure and verify a provider using synthetic data. No core implementation begins until the first integration check succeeds.
- **3. Core implementation:** build input, tailoring, review, copying, and exports incrementally.
- **4. Verification:** test document handling, hostile URLs, provider failures, privacy, accessibility, and output quality.
- **5. Open-source release:** complete the setup and deployment guides and document remaining production requirements.

The repository can be cloned to review and contribute to the design. There is no application to run yet; setup and usage instructions will be added as each stage is completed.

See [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md). Licensed under the [MIT License](LICENSE).
