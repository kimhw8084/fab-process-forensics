"use strict";

const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");
const vm = require("node:vm");

class FakeNode {
  constructor(tagName, id = "") {
    this.tagName = tagName;
    this.id = id;
    this.children = [];
    this.textContent = "";
    this.className = "";
    this.dataset = {};
    this.disabled = false;
    this.open = false;
    this.value = "";
    this.files = [];
    this.listeners = {};
    this.attributes = {};
    this.classes = new Set();
    this.parentNode = null;
    this.style = {};
    this.classList = {
      add: name => this.classes.add(name),
      remove: name => this.classes.delete(name),
      contains: name => this.classes.has(name),
    };
  }

  append(...children) { for (const child of children) child.parentNode = this; this.children.push(...children); }
  replaceChildren(...children) { for (const child of children) child.parentNode = this; this.children = children; }
  remove() { if (this.parentNode) this.parentNode.children = this.parentNode.children.filter(child => child !== this); }
  toJSON() { return { tagName: this.tagName, id: this.id, textContent: this.textContent, className: this.className, children: this.children }; }
  addEventListener(name, handler) { this.listeners[name] = handler; }
  click() { this.clicked = true; }
  setAttribute(name, value) { this.attributes[name] = String(value); }
}

async function main() {
  const demo = JSON.parse(fs.readFileSync("fixtures/case_positive.json", "utf8"));
  const abnormalExample = demo.outcomes.find(item => item.label === "ABNORMAL");
  demo.outcomes.push({ ...abnormalExample, wafer_id: "W3" });
  for (const outcome of demo.outcomes) outcome.lot_id = "LOT-7";
  const outcomeRelation = demo.relationships.find(item => item.id === abnormalExample.relationship_id);
  if (!outcomeRelation.keys.includes("lot_id")) outcomeRelation.keys.push("lot_id");
  demo.events.push({ ...demo.events.find(item => item.wafer_id === abnormalExample.wafer_id), wafer_id: "W3", step_instance_id: "S5" });
  demo.cohort.push("W3");
  demo.coverage.covered_wafer_ids.push("W3");
  const panelSource = fs.readFileSync("ui/p2-panels.js", "utf8")
    .replaceAll("export function ", "function ") + "\nglobalThis.renderP2Contribution = renderP2Contribution; globalThis.buildP2PanelModels = buildP2PanelModels;";
  const source = fs.readFileSync("ui/app.js", "utf8")
    .replace("import { renderP2Contribution } from './p2-panels.js';\n", "");
  const ids = [
    "input-json", "request-status", "download", "preflight", "run", "snapshot-review",
    "snapshot-editor", "snapshot-summary",
    "file-input", "load-demo", "summary", "journeys", "populations", "counterevidence", "evidence",
    "starting-point", "affected-wafer", "affected-wafer-details", "affected-wafer-summary", "affected-lot", "affected-wafer-fields", "affected-lot-fields", "suspected-exposure-fields",
    "exposure-condition-type", "exposure-scope-type", "exposure-chamber", "exposure-tool", "exposure-chamber-fields", "exposure-tool-fields",
    "exposure-start", "exposure-end", "apply-scope",
  ];
  const nodes = Object.fromEntries(ids.map(id => [id, new FakeNode("div", id)]));
  for (const id of ["summary", "journeys", "populations", "counterevidence", "evidence"]) {
    nodes[id].classes.add("empty");
  }
  const document = {
    getElementById(id) { return nodes[id] || (nodes[id] = new FakeNode("div", id)); },
    querySelector() { return { content: "local-state-smoke-token" }; },
    createElement(tag) { return new FakeNode(tag); },
    createTextNode(value) { const node = new FakeNode("#text"); node.textContent = value; return node; },
  };
  document.body = new FakeNode("body", "body");
  document.activeElement = document.body;
  for (const node of Object.values(nodes)) node.focus = () => { document.activeElement = node; };
  const downloadLinks = [];
  const exportBlobs = [];
  const revokedUrls = [];
  const scheduledTimers = [];
  document.createElement = tag => {
    const node = new FakeNode(tag);
    if (tag === "a") downloadLinks.push(node);
    return node;
  };
  const urlApi = {
    createObjectURL(blob) { exportBlobs.push(blob); return "blob:local-state-smoke"; },
    revokeObjectURL(value) { revokedUrls.push(value); },
  };
  const ready = {
    status: "READY_FOR_LOCAL_ANALYSIS",
    limits: { payload_bytes: 100, max_payload_bytes: 1000, event_rows: 4, max_event_rows: 100000, outcome_rows: 2, max_outcome_rows: 100000 },
    source_records: [], relationships: [], scope: {
      target_wafer_ids: ["W2", "W3"], population: ["W1", "W2", "W3"], target_lot_id: "LOT-7",
    }, limitations: [],
  };
  const analysis = {
    status: "VALID", investigation_id: "local-state-smoke", claims: [],
    transformations: [{ id: "p2-journey-and-route-variants-v1", journeys: [{
      wafer_id: "W1", history_status: "COVERAGE_UNKNOWN", route_conformance: "NO_APPROVED_EXPECTED_ROUTE",
      route_segments: [], history_coverage: {}, rework_edges: [], material_relationships: [],
      steps: [{ step_instance_id: "S1", operation: "ETCH", lot_id_at_event: "LOT-A",
               membership_state: "CONFLICTS_WITH_EVENT_ROW_LOT_ID", lot_lineage: {
                 status: "SOURCE_DECLARED_LINEAGE_PATHS_FOUND",
                 material_relationship_coverage: { status: "NOT_ESTABLISHED", assessment: "No material coverage record was supplied." },
                 missing_evidence: [{ reason: "EVENT_LOT_ID_CONFLICTS_WITH_TIME_SCOPED_MEMBERSHIP",
                                      event_lot_id: "LOT-A", candidate_lot_ids: ["LOT-B"] }],
                 seeds: [{ lot_id: "LOT-B", provenance: [{ material_relationship_id: "SPLIT-1" }] }],
               } }],
      lot_lineage_paths: [{
        step_instance_id: "S1", start_lot_id: "LOT-A", end_lot_id: "LOT-B",
        status: "SOURCE_LINKED_AT_EVENT_TIME",
        relationships: [{ record_id: "SPLIT-1", relationship_type: "SPLIT_FROM", traversal_direction: "FROM_TO" }],
      }],
    }], route_variants: [{
      operations: ["ETCH"], wafer_ids: ["W1"], count: 1, order_status: "ORDERED",
      ordered_observed_history_denominator: 1, share_of_ordered_observed_histories: 1,
    }], route_population_summary: {
      coverage_status: "COVERAGE_INCOMPLETE_OR_UNKNOWN",
      declared_covered_population_count: 2, declared_covered_wafer_ids: ["W1", "W2"],
      observed_event_wafer_count: 1, observed_event_wafer_ids: ["W1"],
      ordered_observed_history_denominator: 1, ordered_observed_history_wafer_ids: ["W1"],
      chronology_uncertain_wafer_ids: [], declared_covered_wafer_ids_without_event_rows: ["W2"],
      observed_event_wafer_ids_outside_declared_coverage: [],
      meaning: "Counts describe observed histories only.",
    } }],
    populations: [{ classification: "DEFINITELY_EXPOSED", count: 1, wafer_ids: ["W1"], basis: "exact chamber" }], counterevidence: [{
      question: "Does the selected scope explain the outcome?",
      interpretation: "Descriptive only.", outcome_evidence: [], supporting_observations: [],
      contradicting_observations: { normal_wafers_sharing_exact_exposure: ["W2"] },
      confounders: { equipment: { alternative_equipment_hypotheses: [{
        category: "ALTERNATIVE_EQUIPMENT_PATTERN", status: "DESCRIPTIVE_CANDIDATE_ONLY",
        equipment_type: "TOOL", equipment_id: "T1",
        abnormal_wafers_with_observed_exact_event: ["W1"],
        normal_wafers_with_observed_exact_event: ["W2"],
        abnormal_wafers_without_observed_exact_event: ["W3"],
        normal_wafers_without_observed_exact_event: [],
        potentially_exposed_wafers: [], unknown_wafers: [], population_wafers_missing_outcome: [],
        coverage: { accepted_for_nonmatch_classification: true, assessment: "fixture coverage" },
        observation_event_refs: [{ wafer_id: "W1", step_instance_id: "S1", source_id: "SYN_PROCESS", relationship_id: "SYN_REL" }],
        statistical_association: { status: "NOT_COMPUTED" }, causal_conclusion: { status: "NOT_ESTABLISHED" },
      }] } }, missing_or_ambiguous_evidence: {}, statistical_association: { status: "NOT_COMPUTED" },
      proposed_explanation: { status: "CANDIDATE_FOR_ENGINEER_REVIEW" }, causal_conclusion: { status: "NOT_ESTABLISHED" },
      next_authorized_verification: {
        logical_operation: "read_bounded", purpose: "Reconcile the conflicting time-scoped lot record.",
        selection_rule: "Evidence relevance only; not causal probability.",
        candidates: [{
          rank: 1, category: "LOT_MEMBERSHIP_CONFLICT", logical_operation: "read_bounded",
          purpose: "Reconcile process-row lot values with effective-dated membership edges.",
          maximum_directly_addressed_members: 1, priority_basis: "One wafer has conflicting membership evidence.",
          target_wafer_ids: ["W1"],
          source_relationships: [
            { source_id: "SYN_PROCESS", relationship_id: "SYN_REL_PROCESS", requested_declared_keys: ["wafer_id", "step_instance_id", "lot_id", "timestamp"] },
            { source_id: "SYN_MATERIAL", relationship_id: "SYN_REL_MEMBERSHIP", requested_declared_keys: ["from_entity_id", "to_entity_id"] },
          ],
          distinguishing_value: "Could resolve the lot identity at the event time; cannot establish an exposure effect or root cause.",
          authorization_status: "MUST_BE_CONFIRMED_BY_THE_CONFIGURED_MCP_SERVER", proposed_not_executed: true,
        }],
      },
    }], artifacts: [{
      kind: "investigation_snapshot",
      scope: { target_lot_id: "LOT-7", target_wafer_ids: ["W1", "W2", "W3"] },
      target_outcomes: [{ wafer_id: "W1", label: "NORMAL", lot_id: "LOT-7" }, { wafer_id: "W2", label: "ABNORMAL", lot_id: "LOT-7" }],
      exposure_analysis: {
        scope_type: "CHAMBER", scope_id: "C1", window: { start: "2026-11-21T00:00:00+00:00", end: "2026-11-21T03:00:00+00:00" },
        condition_context: { condition_type: "MAINTENANCE", evidence_status: "CALLER_SUPPLIED_UNVERIFIED" },
        evidence: [], coverage_evidence: { accepted_for_query: true },
      },
    }], sources: [], uncertainty: {}, limitations: [],
    provenance: { input_sha256: "a".repeat(64) },
  };
  let delayNextAnalysis = false;
  let releaseDelayedAnalysis;
  let cancellationRequested = false;
  let analysisRequestHeaders = null;
  async function fetchLocal(url, options = {}) {
    if (url === "/api/demo") return { ok: true, json: async () => demo };
    if (url === "/api/preflight") return { ok: true, json: async () => ready };
    if (url === "/api/cancel") {
      cancellationRequested = true;
      return { ok: true, status: 202, json: async () => ({ status: "CANCELLATION_REQUESTED" }) };
    }
    if (url === "/api/analyze") {
      analysisRequestHeaders = options.headers;
      if (delayNextAnalysis) {
        delayNextAnalysis = false;
        return await new Promise(resolve => { releaseDelayedAnalysis = resolve; });
      }
      return { ok: true, json: async () => analysis };
    }
    throw new Error(`Unexpected local request: ${url}`);
  }
  const context = {
    document, fetch: fetchLocal, TextEncoder, Blob, URL: urlApi, crypto, console, Element: FakeNode,
    window: { setTimeout(callback, delay) { scheduledTimers.push({ callback, delay }); } },
  };
  vm.runInNewContext(panelSource, context, { filename: "ui/p2-panels.js" });
  vm.runInNewContext(source, context, { filename: "ui/app.js" });
  const panelModels = context.buildP2PanelModels(analysis);
  assert.equal(panelModels.summary.status, "VALID");
  assert.equal(panelModels.summary.investigation_id, "local-state-smoke");
  assert.equal(panelModels.journey.journeys[0], analysis.transformations[0].journeys[0], "host data must preserve the exact verified journey object without inventing edges");
  assert.equal(panelModels.exposure.analysis.scope_id, "C1");
  assert.equal(panelModels.counterevidence.investigations[0], analysis.counterevidence[0]);
  assert.equal(panelModels.evidence.snapshot.scope.target_lot_id, "LOT-7");
  assert.equal(panelModels.evidence.input_sha256, "a".repeat(64));
  assert.throws(() => context.buildP2PanelModels(null), /evidence envelope object is required/);
  await new Promise(resolve => setImmediate(resolve));
  assert.match(nodes["input-json"].value, /SYN_PROCESS/);
  assert.equal(nodes["snapshot-editor"].open, false, "raw input must stay collapsed while the concise findings UI is in use");
  assert.match(nodes["snapshot-summary"].textContent, /0\.00 MiB · 5 events · 3 outcomes/, "the collapsed input disclosure must summarize its scope without exposing the full JSON string");
  assert.equal(nodes["affected-wafer"].value, "W2, W3", "the local example should offer its abnormal cohort as a starting point");
  assert.equal(nodes["affected-wafer-details"].open, false, "the selected cohort should stay compact until a reviewer opens the ID editor");
  assert.equal(nodes["affected-wafer-summary"].textContent, "2 selected abnormal wafer IDs · review or edit");
  nodes["affected-wafer"].value = "W3";
  nodes["affected-wafer"].listeners.input();
  assert.equal(nodes["affected-wafer-summary"].textContent, "1 selected abnormal wafer ID · review or edit", "editing the target set must refresh its compact count");
  nodes["affected-wafer"].value = "W2, W3";
  nodes["affected-wafer"].listeners.input();
  await nodes["open-file"].listeners.click();
  assert.equal(nodes["file-input"].clicked, true, "the visible Open JSON file button must activate the native file control");

  nodes["starting-point"].value = "affected-wafer";
  nodes["starting-point"].listeners.change();
  await nodes["apply-scope"].listeners.click();
  let applied = JSON.parse(nodes["input-json"].value);
  assert.equal(applied.wafer_id, "W2", "the first selected abnormal wafer must remain the primary journey anchor");
  assert.deepEqual(applied.target_wafer_ids, ["W2", "W3"], "affected-wafer mode must carry the complete selected cohort");
  assert.ok(applied.cohort.includes("W2"), "affected-wafer mode must retain the target in the comparison population");
  assert.ok(applied.cohort.includes("W3"), "affected-wafer mode must retain every selected target in the comparison population");
  assert.equal(nodes["affected-wafer-details"].open, false, "applying the selected cohort should return its full ID editor to a collapsed state");

  await nodes["load-demo"].listeners.click();
  nodes["starting-point"].value = "affected-lot";
  nodes["starting-point"].listeners.change();
  nodes["affected-lot"].value = "LOT-7";
  await nodes["apply-scope"].listeners.click();
  applied = JSON.parse(nodes["input-json"].value);
  assert.equal(applied.target_lot_id, "LOT-7", "lot mode must retain the caller-selected lot scope");
  assert.deepEqual(applied.target_wafer_ids, ["W1", "W2", "W3"], "lot mode must derive every wafer from explicitly related outcome rows");
  assert.ok(applied.cohort.includes("W1") && applied.cohort.includes("W2") && applied.cohort.includes("W3"), "lot mode must retain all supplied lot outcome wafers in the analysis cohort");
  const missingLotKey = JSON.parse(nodes["input-json"].value);
  missingLotKey.relationships.find(item => item.id === abnormalExample.relationship_id).keys = ["wafer_id"];
  nodes["input-json"].value = JSON.stringify(missingLotKey);
  nodes["input-json"].listeners.input();
  await nodes["apply-scope"].listeners.click();
  assert.match(nodes["request-status"].textContent, /relationship keys include both lot_id and wafer_id|caller-declared approved relationship/);

  await nodes["load-demo"].listeners.click();
  nodes["starting-point"].value = "affected-lot";
  nodes["starting-point"].listeners.change();
  nodes["affected-lot"].value = "LOT-7";
  await nodes["apply-scope"].listeners.click();
  await nodes.preflight.listeners.click();
  assert.equal(nodes.run.disabled, false, "run must unlock after a ready preflight");
  const scopeDisclosure = nodes["snapshot-review"].children.find(child => child.tagName === "details");
  assert.equal(scopeDisclosure.open, false, "large declared scope must stay collapsed during preflight review");
  assert.match(scopeDisclosure.children[0].textContent, /2 target wafer\(s\) · 3 population member\(s\) · lot LOT-7/);
  assert.deepEqual(JSON.parse(scopeDisclosure.children[1].textContent), ready.scope, "the complete original scope remains available without truncation");
  nodes["snapshot-editor"].open = true;
  assert.match(nodes["snapshot-review-announcement"].textContent, /ready for local analysis/, "the compact review result must be announced to screen readers");
  assert.equal(document.activeElement, nodes.run, "ready preflight must move keyboard focus to the analysis action");
  await nodes.run.listeners.click();
  assert.match(analysisRequestHeaders["X-Fabintel-Request-ID"], /^[0-9a-f-]{36}$/i, "analysis requests must carry a cancellable UUID");
  assert.equal(nodes.download.disabled, false, "successful analysis must enable export");
  assert.equal(nodes["snapshot-editor"].open, false, "analysis should return focus to findings and collapse the raw source payload");
  assert.equal(nodes.summary.classes.has("empty"), false, "rendered analysis must replace empty state");
  const investigationNavigation = nodes.summary.children.find(child => child.tagName === "nav");
  assert.equal(investigationNavigation?.attributes["aria-label"], "Investigation section navigation");
  assert.deepEqual(investigationNavigation.children.slice(1).map(link => [link.textContent, link.href]), [
    ["Wafer journey and routes", "#journey-title"],
    ["Exposure populations", "#exposure-title"],
    ["Counterevidence", "#counter-title"],
    ["Sources and evidence", "#sources-title"],
  ], "the compact investigation summary must provide direct links to the four scientific review areas");
  assert.ok(JSON.stringify(nodes.populations.children).includes("CHAMBER C1"), "exposure view must display the selected equipment scope and window");
  assert.ok(JSON.stringify(nodes.populations.children).includes("caller supplied unverified"), "exposure view must distinguish operator condition context from source evidence");
  assert.ok(JSON.stringify(nodes.evidence.children).includes("LOT-7"), "rendered evidence must retain target lot and outcome scope");
  assert.ok(JSON.stringify(nodes.journeys.children).includes("LOT-A"), "journey view must render the source-declared multi-hop lineage start");
  assert.ok(JSON.stringify(nodes.journeys.children).includes("CONFLICT · event row LOT-A; time-scoped membership LOT-B · membership record SPLIT-1"),
    "journey chronology must make a process-row/time-scoped membership conflict visible with the membership record ID");
  assert.ok(JSON.stringify(nodes.journeys.children).includes("SPLIT-1"), "journey view must expose the provenance-bearing lineage edge for review");
  assert.ok(JSON.stringify(nodes.journeys.children).includes("NOT_ESTABLISHED"), "journey view must disclose that absent material edges have no established coverage");
  assert.ok(JSON.stringify(nodes.journeys.children).includes("Declared members with no rows"), "route view must disclose coverage members with no event history");
  assert.ok(JSON.stringify(nodes.counterevidence.children).includes("T1"), "hypothesis view must render the source-verified alternative tool pattern");
  assert.ok(JSON.stringify(nodes.counterevidence.children).includes("W3"), "hypothesis view must render abnormal counterevidence outside the alternative tool pattern");
  assert.ok(JSON.stringify(nodes.counterevidence.children).includes("SYN_REL_PROCESS: wafer_id, step_instance_id, lot_id, timestamp"),
    "the proposed next check must show the process-row keys beside their own relationship");
  assert.ok(JSON.stringify(nodes.counterevidence.children).includes("SYN_REL_MEMBERSHIP: from_entity_id, to_entity_id"),
    "the proposed next check must show material-edge keys separately from process-row keys");
  assert.equal(document.activeElement, nodes.summary, "successful analysis must move focus to the findings summary");
  await nodes.download.listeners.click();
  const exportLinks = downloadLinks.filter(link => link.download);
  assert.equal(exportLinks.length, 1, "export must create one downloadable link in addition to section navigation");
  assert.equal(exportLinks[0].download, "local-state-smoke.json", "export filename must use the investigation ID");
  assert.equal(exportLinks[0].clicked, true, "export must activate the download link");
  assert.equal(exportBlobs.length, 1, "export must serialize the validated result envelope");
  assert.equal(exportBlobs[0].type, "application/json");
  assert.equal(await exportBlobs[0].text(), JSON.stringify(analysis, null, 2) + "\n", "export bytes must preserve the full reproducible evidence envelope");
  assert.match(nodes["request-status"].textContent, /Evidence JSON download started · local-state-smoke\.json/);
  assert.equal(scheduledTimers.length, 1, "export must defer URL cleanup until the browser has time to start the download");
  assert.equal(scheduledTimers[0].delay, 1000);
  scheduledTimers[0].callback();
  assert.deepEqual(revokedUrls, ["blob:local-state-smoke"], "export must revoke its temporary URL after the download starts");

  nodes["input-json"].value = "{}";
  nodes["input-json"].listeners.input();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(cancellationRequested, false, "editing an idle snapshot must not send a cancellation request");
  assert.equal(nodes.run.disabled, true, "editing input must invalidate preflight");
  assert.equal(nodes.download.disabled, true, "editing input must invalidate export");
  assert.equal(nodes.summary.children[0].textContent, "No analysis has been run.", "editing input must clear prior findings");
  assert.equal(nodes.summary.classes.has("empty"), true, "cleared findings must show empty state");

  await nodes["load-demo"].listeners.click();
  nodes["starting-point"].value = "suspected-exposure";
  nodes["starting-point"].listeners.change();
  nodes["exposure-chamber"].value = "C2";
  nodes["exposure-start"].value = "2026-11-21T00:00:00+00:00";
  nodes["exposure-end"].value = "2026-11-21T03:00:00+00:00";
  await nodes["apply-scope"].listeners.click();
  applied = JSON.parse(nodes["input-json"].value);
  assert.deepEqual(applied.suspected_exposure, {
    condition_type: "PROCESS", chamber_id: "C2", start: "2026-11-21T00:00:00+00:00", end: "2026-11-21T03:00:00+00:00",
  }, "exposure mode must apply the selected chamber and timezone-aware window");

  await nodes["load-demo"].listeners.click();
  nodes["starting-point"].value = "suspected-exposure";
  nodes["starting-point"].listeners.change();
  nodes["exposure-scope-type"].value = "tool";
  nodes["exposure-scope-type"].listeners.change();
  nodes["exposure-condition-type"].value = "MAINTENANCE";
  nodes["exposure-tool"].value = "T9";
  nodes["exposure-start"].value = "2026-11-21T00:00:00+00:00";
  nodes["exposure-end"].value = "2026-11-21T03:00:00+00:00";
  await nodes["apply-scope"].listeners.click();
  applied = JSON.parse(nodes["input-json"].value);
  assert.deepEqual(applied.suspected_exposure, {
    condition_type: "MAINTENANCE", tool_id: "T9", start: "2026-11-21T00:00:00+00:00", end: "2026-11-21T03:00:00+00:00",
  }, "maintenance context must remain caller supplied while tool exposure applies only the selected exact tool and window");

  await nodes["load-demo"].listeners.click();
  await nodes["apply-scope"].listeners.click();
  await nodes.preflight.listeners.click();
  cancellationRequested = false;
  delayNextAnalysis = true;
  const inFlight = nodes.run.listeners.click();
  await new Promise(resolve => setImmediate(resolve));
  nodes["input-json"].value = "{}";
  nodes["input-json"].listeners.input();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(cancellationRequested, true, "editing during analysis must request cancellation");
  releaseDelayedAnalysis({ ok: true, json: async () => analysis });
  await inFlight;
  assert.equal(nodes.download.disabled, true, "an in-flight result for an edited snapshot must not be exportable");
  assert.equal(nodes.summary.children[0].textContent, "No analysis has been run.", "an in-flight result must not restore stale findings");

  await nodes["load-demo"].listeners.click();
  await nodes["apply-scope"].listeners.click();
  await nodes.preflight.listeners.click();
  cancellationRequested = false;
  delayNextAnalysis = true;
  const cancellable = nodes.run.listeners.click();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(nodes.run.textContent, "Cancel analysis", "the run control must become a cancel action while analysis is active");
  assert.equal(nodes.run.disabled, false, "the cancel action must remain keyboard-operable while analysis is active");
  const cancelClick = nodes.run.listeners.click();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(cancellationRequested, true, "activating the cancel control must call the local cancel endpoint");
  releaseDelayedAnalysis({ ok: false, status: 409, json: async () => ({ status: "CANCELLED" }) });
  await Promise.all([cancellable, cancelClick]);
  assert.equal(nodes.run.textContent, "Run deterministic analysis", "the run action must return after cancellation");
  assert.equal(nodes.download.disabled, true, "cancelled analysis must not enable evidence export");
  assert.equal(nodes.summary.children[0].textContent, "No analysis has been run.", "cancelled analysis must not render partial findings");

  process.stdout.write(JSON.stringify({
    status: "PASS_LOCAL_UI_STATE_SMOKE",
    node_version: process.version,
    app_script_sha256: crypto.createHash("sha256").update(source).digest("hex"),
    fixture_variant: "Local test harness adds a second synthetic ABNORMAL wafer and explicit lot-keyed outcome relationships.",
    checks: [
      "affected-wafer cohort validates every caller-declared ABNORMAL outcome",
      "lot start derives a cohort only from outcome rows whose declared relationship keys include lot_id and wafer_id",
      "lot start refuses a relationship that does not declare lot membership",
      "suspected-exposure start applies an exact chamber and timezone-aware window",
      "suspected-exposure start applies an exact tool and timezone-aware window",
      "visible Open JSON file action activates the hidden file input",
      "ready preflight enables analysis",
      "ready preflight announces a concise screen-reader summary",
      "ready preflight moves focus to the analysis action",
      "successful analysis enables export",
      "export activates a JSON download with the complete validated envelope and deterministic filename",
      "export cleanup is deferred and the user receives a download-start status",
      "evidence view displays selected lot and outcome scope",
      "journey view displays source-declared lot lineage paths and provenance identifiers",
      "journey view displays material-edge coverage uncertainty",
      "route view reports declared, observed, ordered, uncertain, and no-row denominators separately",
      "hypothesis view displays field-verified alternative equipment patterns and counterexamples",
      "exposure view displays the selected equipment scope and time window",
      "exposure view labels maintenance context as operator supplied and unverified",
      "successful analysis moves focus to findings",
      "input edit invalidates review and clears findings/export",
      "input edit during analysis prevents stale result rendering",
      "analysis requests carry cancellation IDs and edits request cancellation",
      "operator cancellation restores retry control without partial findings or export",
    ],
    scope: "Executes bundled client JavaScript with a local DOM/fetch stub; it is not a real-browser, keyboard, screen-reader, or host-authentication test.",
  }, null, 2) + "\n");
}

main().catch(error => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
