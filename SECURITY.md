# Security Policy

## Supported versions

Only the latest version on the `main` branch is supported.

## Reporting a vulnerability

Please do **not** open a public issue for security problems. Use GitHub's private reporting instead: **Security › Report a vulnerability** on this repository.

Include what you found, how to reproduce it, and its impact. You will get an answer within 7 days.

## Scope notes

- The script parses untrusted `.ai`/PDF files. A file that makes it crash, hang or use excessive memory is in scope.
- The script talks to VectorCraft on `127.0.0.1` only. It sends file paths and receives JSON replies; it does not open network connections elsewhere.
