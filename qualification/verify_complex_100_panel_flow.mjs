#!/usr/bin/env node
/** Cross-stack acceptance for the held-out 100-wafer process-forensics snapshot. */
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { createRequire } from "node:module";
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const fixturePath = resolve(root, "qualification/fixtures/complex_engineer_investigation_v1.json");
const fixtureBytes = readFileSync(fixturePath);
const python = process.env.FABINTEL_PYTHON || "python3";
const output = execFileSync(python, ["-m", "fabintel", "analyze", fixturePath], {
  cwd: root,
  encoding: "utf8",
  maxBuffer: 64 * 1024 * 1024,
});
const evidence = JSON.parse(output);
const requireFromPanelPackage = createRequire(resolve(root, "ui/p2-react/package.json"));
const { JSDOM } = requireFromPanelPackage("jsdom");
const dom = new JSDOM("<!doctype html><main id='journey'></main><main id='exposure'></main><main id='counterevidence'></main>");
globalThis.document = dom.window.document;
globalThis.Element = dom.window.Element;
const { renderP2Counterevidence, renderP2Exposure, renderP2Journey } = await import("../ui/p2-panels.js");

const journey = evidence.transformations.find(item => item.id === "p2-journey-and-route-variants-v1");
const conflictWafer = "SYN-EW-010";
const conflictedJourney = journey.journeys.find(item => item.wafer_id === conflictWafer);
assert.ok(conflictedJourney, "the fixed-answer history must retain the conflicting wafer");
const conflictedSteps = conflictedJourney.steps.filter(item => item.membership_state === "CONFLICTS_WITH_EVENT_ROW_LOT_ID");
assert.deepEqual(conflictedSteps.map(item => item.step_instance_id), ["SYN-EW-010-S02", "SYN-EW-010-S03"]);
assert.ok(conflictedSteps.every(item => item.lot_id_at_event === "SYN-LOT-01"));
assert.ok(conflictedSteps.every(item => item.lot_lineage.seeds.some(seed =>
  seed.provenance.some(ref => ref.material_relationship_id === "SYN-MEM-010-B"),
)));

const journeyRoot = document.querySelector("#journey");
renderP2Journey(journeyRoot, evidence);
const search = journeyRoot.querySelector("#p2-journey-search");
search.value = conflictWafer;
search.dispatchEvent(new dom.window.Event("input", { bubbles: true }));
assert.equal(journeyRoot.querySelectorAll(".journey-page-content > h3").length, 1);
assert.match(journeyRoot.querySelector(".journey-page-status").textContent, /1–1 of 1 matching wafer journeys/);
const filteredJourneyText = journeyRoot.querySelector(".journey-page-content").textContent;
for (const step of conflictedSteps) {
  assert.ok(filteredJourneyText.includes(step.step_instance_id), `filtered journey must show ${step.step_instance_id}`);
  assert.ok(filteredJourneyText.includes("CONFLICT · event row SYN-LOT-01"));
  assert.ok(filteredJourneyText.includes("SYN-MEM-010-B"));
}
const membershipDisclosure = journeyRoot.querySelector(".journey-page-content details");
assert.ok(membershipDisclosure);
membershipDisclosure.open = true;
assert.match(membershipDisclosure.textContent, /SYN-MEM-010-B/);

const hypothesis = evidence.counterevidence[0];
const candidates = hypothesis.next_authorized_verification.candidates;
const membershipProposal = candidates.find(item => item.category === "LOT_MEMBERSHIP_CONFLICT");
assert.ok(membershipProposal, "B05 must keep the conflict follow-up discoverable after journey filtering");
assert.deepEqual(membershipProposal.target_wafer_ids, [conflictWafer]);
assert.deepEqual(membershipProposal.step_instance_refs.map(item => item.step_instance_id), conflictedSteps.map(item => item.step_instance_id));
assert.deepEqual(membershipProposal.material_relationship_refs.map(item => item.record_id), ["SYN-MEM-010-B"]);
assert.equal(membershipProposal.logical_operation, "read_bounded");
assert.equal(membershipProposal.proposed_not_executed, true);
assert.equal(membershipProposal.authorization_status, "MUST_BE_CONFIRMED_BY_THE_CONFIGURED_MCP_SERVER");
const byRelationship = Object.fromEntries(membershipProposal.source_relationships.map(item => [item.relationship_id, item]));
assert.deepEqual(Object.keys(byRelationship).sort(), ["SYN_REL_EW_LOT_MEMBERSHIP", "SYN_REL_EW_PROCESS"]);
assert.ok(byRelationship.SYN_REL_EW_PROCESS.requested_declared_keys.includes("step_instance_id"));
assert.ok(byRelationship.SYN_REL_EW_PROCESS.requested_declared_keys.includes("timestamp"));
assert.ok(byRelationship.SYN_REL_EW_LOT_MEMBERSHIP.requested_declared_keys.includes("from_entity_id"));
assert.ok(!byRelationship.SYN_REL_EW_PROCESS.requested_declared_keys.includes("from_entity_id"));
assert.ok(!byRelationship.SYN_REL_EW_LOT_MEMBERSHIP.requested_declared_keys.includes("step_instance_id"));

const counterRoot = document.querySelector("#counterevidence");
renderP2Counterevidence(counterRoot, evidence);
assert.ok([...counterRoot.querySelectorAll("tbody tr")].some(row => row.textContent.includes("LOT_MEMBERSHIP_CONFLICT")));
const proposalDisclosure = [...counterRoot.querySelectorAll("details")].find(item =>
  item.textContent.includes("Inspect full bounded verification proposals"),
);
assert.ok(proposalDisclosure);
proposalDisclosure.open = true;
assert.match(proposalDisclosure.textContent, /SYN-EW-010-S02/);
assert.match(proposalDisclosure.textContent, /SYN-MEM-010-B/);
assert.match(proposalDisclosure.textContent, /proposed_not_executed/);

const exposure = evidence.artifacts.find(item => item.kind === "investigation_snapshot").exposure_analysis;
assert.equal(exposure.coverage_evidence_level, "CONTRADICTORY");
assert.equal(exposure.definitely_exposed.length, 24);
assert.equal(exposure.potentially_exposed.length, 25);
assert.equal(exposure.unknown.length, 51);
assert.deepEqual(exposure.verified_unexposed, []);
renderP2Exposure(document.querySelector("#exposure"), evidence);
assert.match(document.querySelector("#exposure").textContent, /CONTRADICTORY coverage/);

const exportedEvidence = `${JSON.stringify(evidence, null, 2)}\n`;
const roundTripped = JSON.parse(exportedEvidence);
assert.deepEqual(roundTripped, evidence, "reproducible JSON export must preserve the full evidence envelope");
assert.equal(roundTripped.provenance.input_sha256, evidence.provenance.input_sha256);
assert.equal(roundTripped.counterevidence[0].next_authorized_verification.candidates.length, candidates.length);
assert.equal(roundTripped.artifacts[0].exposure_analysis.coverage_evidence_level, "CONTRADICTORY");
assert.ok(exportedEvidence.includes("SYN-MEM-010-B"));

const summary = {
  status: "PASS_COMPLEX_100_PANEL_FLOW",
  fixture: "qualification/fixtures/complex_engineer_investigation_v1.json",
  fixture_sha256: createHash("sha256").update(fixtureBytes).digest("hex"),
  investigation_id: evidence.investigation_id,
  cohort_wafer_count: journey.journeys.length,
  filtered_conflict_wafer: conflictWafer,
  conflict_step_instances: conflictedSteps.map(item => item.step_instance_id),
  exact_membership_record: "SYN-MEM-010-B",
  membership_proposal_discoverable_after_search: true,
  relationship_keys_kept_separate: true,
  proposal_requires_authorization_and_was_not_executed: true,
  exposure_counts: {
    exact: exposure.definitely_exposed.length,
    potential: exposure.potentially_exposed.length,
    unknown: exposure.unknown.length,
    verified_unexposed: exposure.verified_unexposed.length,
    coverage_evidence_level: exposure.coverage_evidence_level,
  },
  causal_conclusion: hypothesis.causal_conclusion.status,
  evidence_export_bytes: Buffer.byteLength(exportedEvidence),
  evidence_export_sha256: createHash("sha256").update(exportedEvidence).digest("hex"),
  export_round_trip_preserves_provenance_coverage_and_contradictions: true,
  verification_scope: "Synthetic Python engine plus current P2 DOM panel rendering; not a company-source or engineer study.",
};

const reportPath = resolve(root, "qualification/evidence/complex-100-panel-flow.json");
writeFileSync(reportPath, `${JSON.stringify(summary, null, 2)}\n`);
console.log(JSON.stringify(summary, null, 2));
