import assert from "node:assert/strict";
import test from "node:test";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><html><body><main id='summary'></main><main id='journey'></main><main id='exposure'></main><main id='counterevidence'></main></body></html>");
globalThis.document = dom.window.document;
globalThis.Element = dom.window.Element;

const { renderP2Counterevidence, renderP2Exposure, renderP2Journey, renderP2Summary } = await import("../../p2-panels.js");

function sampleEvidence() {
  const journeys = Array.from({ length: 26 }, (_, index) => ({
    wafer_id: `SYN-W-${String(index).padStart(3, "0")}`,
    history_status: "INCOMPLETE",
    route_conformance: "COVERAGE_INCOMPLETE",
    history_coverage: { coverage_evidence_level: "ASSERTED_UNVERIFIED" },
    steps: [{
      step_instance_id: `SYN-W-${String(index).padStart(3, "0")}-S1`,
      operation: "ETCH",
      timestamp: "2026-11-21T01:00:00+00:00",
      source_id: "SYN_PROCESS",
      relationship_id: "SYN_REL_PROCESS",
    }],
    rework_edges: index === 3 ? [{ from_step_instance_id: "S1", to_step_instance_id: "S2" }] : [],
  }));
  return {
    schema_version: "1.0.0",
    investigation_id: "SYN-UI-PAGING",
    product_id: "p2",
    mode: "SYNTHETIC_DEMO",
    status: "PARTIAL",
    claims: Array.from({ length: 26 }, (_, index) => ({
      statement: `Wafer SYN-W-${String(index).padStart(3, "0")} is described by fixed claim ${index}.`,
      category: "DESCRIPTIVE",
      certainty: "CONDITIONAL",
      source_ids: ["SYN_PROCESS"],
      method: "fixed renderer fixture",
    })),
    sources: [{ id: "SYN_PROCESS", approved_semantic_version: "SYN-1", grain: "one step", source_hash: "a".repeat(64) }],
    assumptions: [],
    limitations: ["Synthetic only; no causal conclusion."],
    provenance: { engine_version: "0.3.0", input_sha256: "b".repeat(64) },
    uncertainty: { route_conformance_counts: { COVERAGE_INCOMPLETE: 26 } },
    transformations: [{
      id: "p2-journey-and-route-variants-v1",
      journeys,
      route_variants: [{ count: 26, operations: ["ETCH"], wafer_ids: journeys.map(item => item.wafer_id) }],
      route_population_summary: { coverage_evidence_level: "ASSERTED_UNVERIFIED" },
    }],
    artifacts: [{
      kind: "investigation_snapshot",
      scope: { target_wafer_ids: ["SYN-W-003", "SYN-W-023"] },
      exposure_analysis: {
        population: journeys.map(item => item.wafer_id),
        definitely_exposed: ["SYN-W-003"],
        potentially_exposed: ["SYN-W-004"],
        unknown: journeys.slice(5).map(item => item.wafer_id),
        verified_unexposed: [],
        coverage_evidence_level: "ASSERTED_UNVERIFIED",
      },
    }],
    counterevidence: [{
      causal_conclusion: { status: "NOT_ESTABLISHED" },
      next_authorized_verification: { purpose: "Check the synthetic coverage source after server authorization." },
    }],
  };
}

test("standalone panels summarize first, paginate journeys, search by wafer, and preserve evidence", () => {
  const evidence = sampleEvidence();
  const originalEvidence = JSON.stringify(evidence);
  const summaryRoot = document.querySelector("#summary");
  const journeyRoot = document.querySelector("#journey");

  renderP2Summary(summaryRoot, evidence);
  const claimDisclosure = summaryRoot.querySelector("details");
  assert.ok(claimDisclosure);
  assert.equal(claimDisclosure.open, false);
  assert.equal(claimDisclosure.querySelectorAll("tbody tr").length, 26);
  assert.match(summaryRoot.querySelector("table caption").textContent, /cohort triage and evidence coverage/);
  assert.match(summaryRoot.textContent, /Verified unexposed comparators/);
  assert.match(summaryRoot.textContent, /NOT_ESTABLISHED/);

  renderP2Journey(journeyRoot, evidence);
  const pageContent = journeyRoot.querySelector(".journey-page-content");
  const pageStatus = journeyRoot.querySelector(".journey-page-status");
  const previous = journeyRoot.querySelector(".journey-page-buttons button:first-child");
  const next = journeyRoot.querySelector(".journey-page-buttons button:last-child");
  const search = journeyRoot.querySelector("#p2-journey-search");
  assert.equal(pageContent.querySelectorAll(":scope > h3").length, 10);
  assert.equal(pageStatus.textContent, "Showing 1–10 of 26 wafer journeys.");
  assert.equal(previous.disabled, true);
  assert.equal(next.disabled, false);

  next.click();
  assert.equal(pageContent.querySelectorAll(":scope > h3").length, 10);
  assert.equal(pageContent.querySelector(":scope > h3").textContent.startsWith("Wafer SYN-W-010"), true);
  assert.equal(pageStatus.textContent, "Showing 11–20 of 26 wafer journeys.");
  previous.click();
  assert.equal(pageStatus.textContent, "Showing 1–10 of 26 wafer journeys.");

  search.value = "SYN-W-023";
  search.dispatchEvent(new dom.window.Event("input", { bubbles: true }));
  assert.equal(pageContent.querySelectorAll(":scope > h3").length, 1);
  assert.match(pageContent.querySelector(":scope > h3").textContent, /SYN-W-023/);
  assert.equal(pageStatus.textContent, "Showing 1–1 of 1 matching wafer journeys.");
  search.value = "does-not-exist";
  search.dispatchEvent(new dom.window.Event("input", { bubbles: true }));
  assert.equal(pageStatus.textContent, "Showing 0 wafer journeys.");
  assert.match(pageContent.textContent, /No wafer journeys match/);

  assert.equal(JSON.stringify(evidence), originalEvidence, "panel state must not alter the source evidence envelope");
});

test("journey chronology makes conflicting event-row and time-scoped lot evidence explicit", () => {
  const evidence = sampleEvidence();
  const step = evidence.transformations[0].journeys[0].steps[0];
  step.lot_id_at_event = "LOT-A";
  step.membership_state = "CONFLICTS_WITH_EVENT_ROW_LOT_ID";
  step.lot_lineage = {
    missing_evidence: [{
      reason: "EVENT_LOT_ID_CONFLICTS_WITH_TIME_SCOPED_MEMBERSHIP",
      event_lot_id: "LOT-A",
      candidate_lot_ids: ["LOT-B"],
    }],
    seeds: [{ lot_id: "LOT-B", provenance: [{ material_relationship_id: "MEM-LOT-B" }] }],
  };
  const journeyRoot = document.querySelector("#journey");
  renderP2Journey(journeyRoot, evidence);
  const table = [...journeyRoot.querySelectorAll("table")].find(item =>
    item.querySelector("caption")?.textContent.includes("Chronological process step instances"));
  assert.ok(table);
  const headers = [...table.querySelectorAll("thead th")].map(item => item.textContent);
  const lotColumn = headers.indexOf("Lot evidence at event");
  assert.notEqual(lotColumn, -1, "the primary chronology must identify this cell as evidence, not an unqualified lot value");
  assert.equal(table.querySelector("tbody tr td:nth-child(5)").textContent,
    "CONFLICT · event row LOT-A; time-scoped membership LOT-B · membership record MEM-LOT-B");
});

test("exposure and next-check panels keep uncertainty explicit and population lists inspectable", () => {
  const members = Array.from({ length: 26 }, (_, index) => `SYN-W-${String(index).padStart(3, "0")}`);
  const evidence = {
    status: "PARTIAL",
    populations: [
      { classification: "EXPOSED", count: 1, wafer_ids: [members[0]], basis: "Exact declared scope and time match." },
      { classification: "POTENTIALLY_EXPOSED", count: 1, wafer_ids: [members[1]], basis: "Uncertain event time." },
      { classification: "UNKNOWN", count: 24, wafer_ids: members.slice(2), basis: "Coverage is not verified." },
    ],
    artifacts: [{ kind: "investigation_snapshot", exposure_analysis: {
      scope_type: "CHAMBER", scope_id: "SYN-C1", window: { start: "2026-11-21T00:00:00Z", end: "2026-11-21T02:00:00Z" },
      coverage_evidence_level: "CONTRADICTORY", coverage_reason: "Missing rows are named.",
      evidence: [
        { wafer_id: members[0], step_instance_id: "SYN-S1", classification: "EXACT_CHAMBER_WINDOW_MATCH", timestamp_utc: "2026-11-21T01:00:00Z", source_id: "SYN_PROCESS", relationship_id: "SYN_REL_PROCESS" },
        { wafer_id: members[1], step_instance_id: "SYN-S2", classification: "TIME_BOUNDARY_UNCERTAIN", timestamp_utc: "2026-11-21T02:00:00Z", source_id: "SYN_PROCESS", relationship_id: "SYN_REL_PROCESS" },
        { wafer_id: members[2], step_instance_id: "SYN-S3", classification: "SOURCE_RELATIONSHIP_EFFECTIVITY_UNCERTAIN", timestamp_utc: "2026-11-21T01:00:00Z", source_id: "SYN_PROCESS", relationship_id: "SYN_REL_PROCESS" },
      ],
      coverage_evidence: { record_id: "SYN-COVERAGE", missing_record_ids: ["GAP-1"] },
      condition_event_status: "NO_CONDITION_EVENT_RECORDS_SUPPLIED", condition_event_evidence: [],
    } }],
    transformations: [{
      id: "p2-journey-and-route-variants-v1",
      journeys: members.slice(2, 25).map(wafer_id => ({ wafer_id, steps: [] })),
    }],
    counterevidence: [{
      question: "Does the candidate interval explain the observed outcome?",
      next_authorized_verification: {
        selection_rule: "Rank follows evidence relevance, not causal probability.",
        candidates: [{
          rank: 1, category: "EXPOSURE_COVERAGE", logical_operation: "read_bounded",
          purpose: "Reconcile source coverage.", maximum_directly_addressed_members: 24,
          target_wafer_ids: members.slice(2), requested_declared_keys: ["missing_record_ids"],
          source_relationships: [{ source_id: "SYN_COVERAGE", relationship_id: "SYN_REL_COVERAGE" }],
          distinguishing_value: "Could distinguish observed nonmatches from missing process records.",
          authorization_status: "MUST_BE_CONFIRMED_BY_THE_CONFIGURED_MCP_SERVER", proposed_not_executed: true,
        }, {
          rank: 2, category: "LOT_MEMBERSHIP_CONFLICT", logical_operation: "read_bounded",
          purpose: "Reconcile the event-row lot with its time-scoped membership edge.",
          maximum_directly_addressed_members: 1, target_wafer_ids: [members[0]],
          source_relationships: [{ source_id: "SYN_PROCESS", relationship_id: "SYN_REL_PROCESS", requested_declared_keys: ["wafer_id", "step_instance_id", "lot_id", "chamber_id", "timestamp"] }],
          step_instance_refs: [{ source_id: "SYN_PROCESS", relationship_id: "SYN_REL_PROCESS", step_instance_id: "SYN-S1" }],
          review_factors: { step_instance_ref_count: 1, bounded_read_request_count_proxy: 2, coverage_evidence_level: "ASSERTED_UNVERIFIED", negative_evidence_interpretation_risk: "HIGH" },
          covers_additional_checks: [{ category: "UNKNOWN_CHAMBER", purpose: "Verify chamber assignment.", question: "Which chamber processed this step?", distinguishing_value: "May resolve exact chamber identity.", priority_basis: "One unresolved step." }],
          distinguishing_value: "Could verify this exact process step; does not establish cause.",
          authorization_status: "MUST_BE_CONFIRMED_BY_THE_CONFIGURED_MCP_SERVER", proposed_not_executed: true,
        }],
      },
    }],
  };

  const exposureRoot = document.querySelector("#exposure");
  renderP2Exposure(exposureRoot, evidence);
  assert.match(exposureRoot.textContent, /SOURCE_VERIFIED coverage/);
  assert.match([...exposureRoot.querySelectorAll("table caption")].map(item => item.textContent).join(" "), /Source-linked process records/);
  assert.match(exposureRoot.textContent, /Clock uncertainty crosses the selected window boundary/);
  assert.match(exposureRoot.textContent, /No process-history rows in this snapshot/);
  assert.match(exposureRoot.textContent, /No selected-window match observed under incomplete coverage/);
  assert.match(exposureRoot.textContent, /Required source relationship or time effectivity unresolved/);
  const unknownCard = [...exposureRoot.querySelectorAll(".population")].find(card => card.textContent.includes("UNKNOWN"));
  assert.ok(unknownCard);
  assert.match(unknownCard.textContent, /and 19 more/);
  assert.equal(unknownCard.querySelector("details").open, false);
  assert.equal(unknownCard.querySelector("details pre").textContent.split("\n").length, 24);

  const counterRoot = document.querySelector("#counterevidence");
  renderP2Counterevidence(counterRoot, evidence);
  assert.match(counterRoot.textContent, /Ranked next authorized checks · proposals only/);
  assert.match(counterRoot.textContent, /SYN_COVERAGE \/ SYN_REL_COVERAGE/);
  assert.match(counterRoot.textContent, /read_bounded/);
  assert.match(counterRoot.textContent, /MUST_BE_CONFIRMED_BY_THE_CONFIGURED_MCP_SERVER/);
  assert.match(counterRoot.textContent, /Could distinguish observed nonmatches from missing process records/);
  assert.match(counterRoot.textContent, /LOT_MEMBERSHIP_CONFLICT \+ UNKNOWN_CHAMBER/);
  assert.match(counterRoot.textContent, /2 read-pair proxy/);
  assert.match(counterRoot.textContent, /ASSERTED_UNVERIFIED coverage/);
  assert.match(counterRoot.textContent, /HIGH negative-evidence risk/);
  assert.equal(counterRoot.querySelectorAll("#counterevidence table tbody tr").length > 0, true);
});

test("large evidence tables are paged and route population membership stays collapsed", () => {
  const evidence = sampleEvidence();
  evidence.claims = Array.from({ length: 250 }, (_, index) => ({
    statement: `Synthetic observation ${index + 1}`,
    category: "DESCRIPTIVE",
    certainty: "CONDITIONAL",
    source_ids: ["SYN_PROCESS"],
    method: "fixed large-table fixture",
  }));
  const memberIds = Array.from({ length: 250 }, (_, index) => `SYN-W-${String(index + 1).padStart(4, "0")}`);
  evidence.transformations[0].route_variants = [{
    count: memberIds.length,
    operations: ["ETCH", "CLEAN"],
    wafer_ids: memberIds,
    order_status: "ORDERED",
    ordered_observed_history_denominator: memberIds.length,
    share_of_ordered_observed_histories: 1,
  }];
  evidence.transformations[0].route_population_summary = {
    coverage_status: "ASSERTED_UNVERIFIED",
    declared_covered_wafer_ids: memberIds,
    observed_event_wafer_ids: memberIds.slice(0, 220),
    ordered_observed_history_wafer_ids: memberIds.slice(0, 200),
    chronology_uncertain_wafer_ids: memberIds.slice(200, 220),
    declared_covered_wafer_ids_without_event_rows: memberIds.slice(220),
    observed_event_wafer_ids_outside_declared_coverage: [],
    meaning: "Caller assertion remains unverified.",
  };
  const original = JSON.stringify(evidence);

  const summaryRoot = document.querySelector("#summary");
  renderP2Summary(summaryRoot, evidence);
  const claimsDisclosure = [...summaryRoot.querySelectorAll("details")].find(item => item.textContent.includes("Inspect all 250"));
  claimsDisclosure.open = true;
  const claimsTable = [...claimsDisclosure.querySelectorAll("table")].find(item => item.caption.textContent.includes("Claims retained"));
  assert.equal(claimsTable.querySelectorAll("tbody tr").length, 100);
  const claimsControls = [...claimsDisclosure.querySelectorAll("nav")].find(item => item.getAttribute("aria-label")?.includes("Claims retained"));
  assert.equal(claimsControls.querySelector("[role=status]").textContent, "Rows 1–100 of 250");
  const [previous, next] = claimsControls.querySelectorAll("button");
  assert.equal(previous.disabled, true);
  next.click();
  assert.equal(claimsTable.querySelectorAll("tbody tr").length, 100);
  assert.equal(claimsControls.querySelector("[role=status]").textContent, "Rows 101–200 of 250");
  assert.match(claimsTable.querySelector("tbody tr:first-child").textContent, /Synthetic observation 101/);
  previous.click();
  assert.equal(claimsControls.querySelector("[role=status]").textContent, "Rows 1–100 of 250");
  assert.equal(JSON.stringify(evidence), original, "rendering must not mutate evidence arrays or records");

  const journeyRoot = document.querySelector("#journey");
  renderP2Journey(journeyRoot, evidence);
  const variantText = [...journeyRoot.querySelectorAll("p")].find(item => item.textContent.includes("members · sample"));
  assert.ok(variantText);
  assert.match(variantText.textContent, /250 members · sample SYN-W-0001, SYN-W-0002/);
  assert.doesNotMatch(variantText.textContent, /SYN-W-0250/);
  const variantDetails = [...journeyRoot.querySelectorAll("details")].find(item => item.textContent.includes("Inspect all 250 wafers in route variant"));
  assert.ok(variantDetails);
  assert.equal(variantDetails.open, false);
  assert.equal(variantDetails.querySelector("pre").textContent.split("\n").length, 250);
  const denominatorDetails = [...journeyRoot.querySelectorAll("details")].find(item => item.textContent.includes("complete route-population member sets"));
  assert.ok(denominatorDetails);
  assert.equal(denominatorDetails.open, false);
  assert.equal(JSON.parse(denominatorDetails.querySelector("pre").textContent).declared_covered_wafer_ids.length, 250);
});

test("competing equipment table samples populations while retaining full membership in collapsed evidence", () => {
  const abnormalMembers = Array.from({ length: 120 }, (_, index) => `SYN-ABN-${String(index + 1).padStart(3, "0")}`);
  const normalMembers = Array.from({ length: 80 }, (_, index) => `SYN-NRM-${String(index + 1).padStart(3, "0")}`);
  const evidence = {
    counterevidence: [{
      question: "Could an alternate equipment pattern distinguish the hypotheses?",
      interpretation: "Population overlap is descriptive and is limited by source coverage.",
      confounders: { equipment: { alternative_equipment_hypotheses: [{
        equipment_type: "CHAMBER",
        equipment_id: "SYN-C7",
        abnormal_wafers_with_observed_exact_event: abnormalMembers,
        normal_wafers_with_observed_exact_event: normalMembers,
        abnormal_wafers_without_observed_exact_event: [],
        coverage: { accepted_for_nonmatch_classification: false },
      }] } },
    }],
  };
  const root = document.querySelector("#counterevidence");

  renderP2Counterevidence(root, evidence);

  const patterns = [...root.querySelectorAll("table")].find(item => item.caption.textContent.includes("alternate equipment patterns"));
  const row = patterns.querySelector("tbody tr");
  assert.match(row.textContent, /120 member\(s\) · sample SYN-ABN-001, SYN-ABN-002, SYN-ABN-003, SYN-ABN-004, SYN-ABN-005, SYN-ABN-006 …/);
  assert.match(row.textContent, /80 member\(s\) · sample SYN-NRM-001/);
  assert.doesNotMatch(row.textContent, /SYN-ABN-120|SYN-NRM-080/);
  assert.match(row.textContent, /Incomplete \/ unknown/);

  const evidenceDetails = [...root.querySelectorAll("details")].find(item => item.textContent.includes("Inspect CHAMBER SYN-C7"));
  assert.ok(evidenceDetails);
  assert.equal(evidenceDetails.open, false);
  const candidate = JSON.parse(evidenceDetails.querySelector("pre").textContent);
  assert.equal(candidate.abnormal_wafers_with_observed_exact_event.length, 120);
  assert.equal(candidate.normal_wafers_with_observed_exact_event.length, 80);
  assert.equal(JSON.stringify(evidence).includes("SYN-ABN-120"), true);
});
