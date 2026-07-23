# Security Policy

KnowledgeHub AI is a personal/portfolio project, not a production service
with paying users or hosted infrastructure -- there is no live deployment
to protect, and this policy is scoped accordingly. That said, the code is
public and meant to demonstrate real engineering practice, so security
issues are taken seriously and fixed promptly.

## Supported versions

Only the latest frozen milestone (see the most recent tag and
[`CHANGELOG.md`](CHANGELOG.md)) receives fixes. There is no long-term
support for older milestone tags.

## Reporting a vulnerability

Please **do not open a public GitHub issue** for security
vulnerabilities. Instead, email **saibalaji250904@gmail.com** with:

- A description of the vulnerability and its potential impact.
- Steps to reproduce it (a minimal repro is ideal).
- Which milestone/tag/commit you tested against.

You should get an acknowledgment within a few days. Since this is a
solo-maintained project, there's no guaranteed SLA, but a fix or a
mitigation plan will follow as soon as reasonably possible, and you'll be
credited in the fix's changelog entry unless you'd prefer otherwise.

## Scope and known limitations

Some things are intentional, documented scope decisions rather than
vulnerabilities -- see the relevant ADR before reporting:

- No OCR fallback for scanned PDFs without a text layer is a deliberate
  MVP scope cut (ADR-0006), not a bug.
- Local file storage on a Docker volume, not S3/object storage
  (ADR-0007) -- expected for local/demo use.
- The default local embedding provider and the extractive LLM fallback
  are intentionally zero-dependency/zero-API-key defaults (ADR-0004);
  they are not meant to represent production-grade answer quality.
- Workspace isolation (every document/answer/concept query is scoped to
  the authenticated session's workspace) is a security-relevant property
  that **is** in scope -- if you find a way to read, modify, or delete
  another workspace's data, that's a genuine report worth sending.
