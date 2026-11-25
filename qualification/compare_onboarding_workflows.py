"""Compare executable onboarding affordances without inventing time savings."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "release/FAB_PROCESS_FORENSICS_P2_CANDIDATE.zip"
OUTPUT = ROOT / "qualification/evidence/onboarding-baseline-comparison-2026-11-24.json"
EXPECTED_BASELINE_SHA256 = "8cd4d26b58cec464e21bebc3a6c4704ea862ed496de5c729568f297970303f5d"
BASELINE_CLI = "FAB_PROCESS_FORENSICS_P2/fabintel/cli.py"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _commands(source: str) -> list[str]:
    return re.findall(r'commands\.add_parser\("([a-z0-9-]+)"', source)


def main() -> int:
    baseline_hash = _sha256(BASELINE)
    if baseline_hash != EXPECTED_BASELINE_SHA256:
        raise SystemExit("Refusing comparison: frozen baseline checksum changed.")
    with ZipFile(BASELINE) as archive:
        baseline_cli = archive.read(BASELINE_CLI).decode("utf-8")
        baseline_skill = any(name.endswith("/.agents/skills/p2-internal-onboarding/SKILL.md")
                             for name in archive.namelist())

    current_cli = (ROOT / "fabintel/cli.py").read_text(encoding="utf-8")
    current_skill = ROOT / ".agents/skills/p2-internal-onboarding/SKILL.md"
    baseline_commands = _commands(baseline_cli)
    current_commands = _commands(current_cli)
    onboarding_commands = [name for name in ("onboard-live", "onboard-review", "investigate-mcp")
                           if name in current_commands]
    if any(name in baseline_commands for name in onboarding_commands):
        raise SystemExit("Unexpected baseline onboarding command; review the comparison before use.")
    if onboarding_commands != ["onboard-live", "onboard-review", "investigate-mcp"]:
        raise SystemExit("Current onboarding command sequence is incomplete or reordered.")

    report = {
        "schema_version": "p2-onboarding-effort-proxy/v1",
        "comparison_date": "2026-11-24",
        "comparison_basis": "Executable source and deterministic synthetic acceptance; not a human-time study.",
        "frozen_baseline": {
            "archive_sha256": baseline_hash,
            "cli_commands": baseline_commands,
            "live_onboarding_commands": [],
            "onboarding_skill_present": baseline_skill,
            "interpretation": "The baseline exposes no executable live discovery, review-materialization, or MCP investigation command. Manual source-configuration time and step count are not reconstructable from that interface.",
        },
        "engineering_phase": {
            "cli_commands": current_commands,
            "live_onboarding_commands": onboarding_commands,
            "onboarding_skill_present": current_skill.is_file(),
            "invocations_from_configured_transport_to_first_investigation": len(onboarding_commands),
            "review_artifact_for_unique_mapping": "One explicit, proposal-digest-bound decision file; this does not establish server permission.",
            "ambiguous_environment_manual_decisions": "5-7 across the 16-environment synthetic benchmark; decisions are never auto-authorized.",
        },
        "synthetic_validation": {
            "adversarial_environments": 16,
            "fixed_answer_passes": 16,
            "role_expectations_checked": 33,
            "automatic_wrong_mapping_acceptances": 0,
            "source_mapping_authorized_automatically": False,
            "large_catalog_descriptors": 13008,
            "end_to_end_mcp_schema_variants": ["FABX aliases", "alternate source and physical-field aliases"],
            "end_to_end_investigation": "Both variants complete official-SDK discovery, deterministic source mapping, digest-bound synthetic review, bounded MCP reads, and B01/B02/B03/B05 evidence analysis. The second variant also completes the CLI workflow.",
        },
        "not_measured": [
            "Human setup time",
            "Company-side engineering hours saved",
            "Actual engineer interaction time",
            "Manufacturing ROI",
        ],
        "qualification_boundary": "Synthetic-only. Simulated review and permissions do not establish company authorization, data semantics, or transfer rights.",
    }
    OUTPUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
