# Deployment path

The current application is designed for one person on their own computer. It binds to loopback, uses a process-wide local token, and does not provide user accounts or tenant isolation. **Do not expose it directly to the public internet.**

Before a hosted deployment, build and verify:

1. Authentication, per-user authorization, and session-scoped request protection.
2. HTTPS, rate limits, abuse controls, bounded queues, and clear provider spending controls.
3. Isolated document parsing with operating-system resource limits on the target platform, plus restricted outbound networking for URL imports.
4. Explicit data retention, deletion, logging-redaction, and incident-response policies; use a proper secrets manager for any infrastructure credentials.
5. Automated deployment and monitoring that exclude resumes and keys from logs, followed by an independent security review and load testing.

Provider API keys belong to individual users in the current design. A hosted version must explain who can access those keys and resume contents, how long data is retained, and the provider's terms. This repository does not yet provide a production deployment configuration.

## Continuous integration

The [example workflow](examples/ci.yml) is not active. To enable it, copy it into `.github/workflows/` and push with a GitHub credential that has permission to create or update workflows. Check the resulting runs before claiming the app has been tested on each operating system.
