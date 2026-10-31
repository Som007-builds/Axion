# Security policy

Axion is a self-hosted research prototype and is **not hardened for public
internet exposure**. The deployment guidance in the
[README](README.md#security-considerations) is part of this policy.

## Supported versions

Only the `main` branch is maintained. There are no backported security releases.

## Reporting a vulnerability

Please **do not open a public issue** for a vulnerability.

Use GitHub's private vulnerability reporting on this repository
(**Security → Report a vulnerability**). Include:

- the affected endpoint, file, or configuration,
- steps to reproduce,
- the impact you believe it has,
- any suggested mitigation.

You can expect an initial response within a few days. This is a single-maintainer
project, so please allow reasonable time before public disclosure.

## In scope

- Authentication and authorization bypass on write, compute, or job routes
- Secret leakage into the client bundle or logs
- Injection through the API, ingestion pipeline, or graph queries
- Unsafe deserialization or file handling in PDF ingestion
- Denial of service that is not simply "the LLM is slow"

## Out of scope

- Missing TLS, multi-tenancy, per-user quotas, or observability — these are
  documented limitations, not vulnerabilities.
- Prompt-injection effects that only change the wording of an LLM summary.
- Findings that require the attacker to already hold `AXION_API_KEY` or shell
  access to the host.
