# AI assistance disclosure

Parts of this repository were written with AI coding assistants. This file
says which, for what, and who is responsible.

## Tools

- **OpenAI Codex** — used during the original build (February–April 2026). The
  commit history still shows it: a Telegram/Codex remote-control bridge was
  added and later removed (`0105c9f` … `1ead9b1`), and several commits are
  session checkpoints rather than reviewed units of work.
- **Anthropic Claude Code** — used for the September 2026 read-only audit of
  this codebase and for the upgrade series that starts at PR #1 (dependency
  pins, first-run fixes, security fixes, tests, documentation).

## What the assistants did

Drafted code, tests and documentation from the author's specifications;
audited the codebase and produced the findings that drive the upgrade
roadmap; proposed fixes that the author reviewed before they were committed.

## What the author did

Defined the product and its scope; chose the architecture (local-first
runtime, one shared camera manager feeding gate and driver pipelines, SQLite,
InsightFace + YOLO + MediaPipe); set the operating thresholds and policies;
reviewed, ran and tested every change on the target machine before merging
it; and is responsible for every line in this repository, including the bugs
the audit found.

## Reading the history

From PR #1 onward, commits follow Conventional Commits and each pull request
states how it was verified. Earlier commits ("checkpoint", "Session: …",
"stage", "2") are kept as they were written; published history is not
rewritten.

## Reporting

If you find a defect that looks machine-generated, report it the same way as
any other bug (see `SECURITY.md` for security issues once it exists, otherwise
open an issue). Provenance does not change severity or ownership.
