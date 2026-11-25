---
name: p2-offline-release
description: Qualify, install, secure, and package the P2 product and its selected dependencies with reproducible offline evidence.
---

# P2 offline and release qualification

Use this skill for dependency selection, source/license review, offline setup, security checks, release gates, or artifact packaging.

1. Reuse the standard-library baseline and currently installed/approved tools first. Add a dependency only after a task-matched correctness/performance comparison shows measurable value or a protocol capability requires it.
2. For each selected dependency, pin a source commit/release and artifact hashes; inspect direct and transitive licenses, package contents, platform support, security advisories, build/install behavior, and runtime egress. Candidate inventory is not approval.
3. Keep all chosen source references, locks, wheels, notices, SBOM, test scripts, and receipts inside the product folder. A remote cache or public repository is not part of the offline deliverable.
4. Recreate a clean environment using only the staged local package set, with public network unavailable. Verify dependency checks, protocol or browser behavior, and deterministic model-off workflow on every claimed OS/architecture.
5. Run release checks from executable commands and inspect their machine-readable outputs. Preserve FAIL, NOT_RUN, NOT_VERIFIED, and PENDING_INTERNAL states; no aggregate score can compensate for a scientific, authorization, or security failure.
6. Verify reproducible source manifest, archive content, checksums, install/uninstall/rollback, and stop behavior. Do not label a candidate transfer-ready while an external release-critical gate remains.

Relevant adaptations: `research/golden-agentic-engineering/opencode-skills/golden-offline-toolchain.SKILL.md`, `golden-release.SKILL.md`, `standards/rules.json`, and `standards/release.json`. Golden is a prequalification pilot; company target OS, security feeds, OSS approval, and deployment authorization must be qualified separately.
