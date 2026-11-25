import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { JSDOM } from "jsdom";

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const evidence = JSON.parse(fs.readFileSync(path.join(projectRoot, "qualification/evidence/mcp-end-to-end-workflow.json"), "utf8"));
const dom = new JSDOM("<!doctype html><html><body><div id=app></div></body></html>", { url: "http://localhost/" });
globalThis.window = dom.window;
globalThis.document = dom.window.document;
globalThis.HTMLElement = dom.window.HTMLElement;
globalThis.Node = dom.window.Node;
Object.defineProperty(globalThis, "navigator", { configurable: true, value: dom.window.navigator });
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const React = await import("react");
const act = React.act ?? (await import("react-dom/test-utils")).act;
const { createRoot } = await import("react-dom/client");
const { P2ProcessForensicsPanels, buildP2PanelModels, summarizeMembershipRefresh } = await import("../dist/index.js");

function mount(props) {
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  act(() => root.render(React.createElement(P2ProcessForensicsPanels, props)));
  return { host, root, unmount: () => act(() => root.unmount()) };
}

function expandJourneyEvidence(waferCount, stepsPerWafer) {
  const expanded = structuredClone(evidence);
  const journey = expanded.transformations.find(item => item.id === "p2-journey-and-route-variants-v1");
  const templates = journey.journeys;
  journey.journeys = Array.from({ length: waferCount }, (_, waferIndex) => {
    const template = templates[waferIndex % templates.length];
    const waferId = `SYN-PAGE-W${waferIndex + 1}`;
    const steps = Array.from({ length: stepsPerWafer }, (_, stepIndex) => ({
      ...structuredClone(template.steps[stepIndex % template.steps.length]),
      wafer_id: waferId,
      step_instance_id: `${waferId}-S${stepIndex + 1}`,
      timestamp: new Date(Date.UTC(2026, 10, 21, 0, 0) + (waferIndex * stepsPerWafer + stepIndex) * 60_000).toISOString(),
    }));
    return {
      ...structuredClone(template),
      wafer_id: waferId,
      steps,
      route_segments: (template.route_segments ?? []).map(segment => ({
        ...structuredClone(segment),
        step_instance_ids: steps.map(step => step.step_instance_id),
      })),
      rework_edges: [],
    };
  });
  return expanded;
}

function HostTable({ caption, columns, rows, onInspectEvidence }) {
  return React.createElement("div", { "data-p1-table": caption },
    React.createElement("table", null,
      React.createElement("caption", null, caption),
      React.createElement("thead", null, React.createElement("tr", null, columns.map(name => React.createElement("th", { key: name, scope: "col" }, name)))),
      React.createElement("tbody", null, rows.map(row => React.createElement("tr", { key: row.id },
        ...row.cells.map((cell, index) => React.createElement("td", { key: `${row.id}-${index}` }, cell)),
        ...(columns.includes("Evidence inspector") ? [React.createElement("td", { key: `${row.id}-evidence-cell` }, (row.evidenceRefs ?? []).map((reference, index) => React.createElement("button", {
          key: `${row.id}-evidence-${index}`, type: "button", onClick: () => onInspectEvidence?.(reference),
        }, `Inspect ${reference.recordId ?? reference.sourceId ?? reference.relationshipId ?? "evidence"}`))) ] : []),
      ))),
    ),
  );
}

function HostTimeline({ journeys }) {
  return React.createElement("div", { "data-p1-journey-timeline": true }, journeys.map(item =>
    React.createElement("p", { key: item.wafer_id }, `${item.wafer_id}: ${item.steps.map(step => step.step_instance_id).join(", ")}`),
  ));
}

test("typed models preserve evidence references and do not mutate the source envelope", () => {
  const before = JSON.stringify(evidence);
  const models = buildP2PanelModels(evidence);
  assert.equal(JSON.stringify(evidence), before);
  assert.equal(models.summary.investigation_id, evidence.investigation_id);
  assert.equal(models.evidence.input_sha256, evidence.provenance.input_sha256);
  assert.equal(models.exposure.analysis.coverage_evidence_level, "ASSERTED_UNVERIFIED");
  assert.deepEqual(models.exposure.analysis.verified_unexposed, []);
  assert.strictEqual(models.journey.journeys[0], evidence.transformations.find(item => item.id === "p2-journey-and-route-variants-v1").journeys[0]);
  assert.ok(models.exposure.analysis.evidence.every(row => row.source_id && row.relationship_id));
});

test("refreshed membership summaries preserve unresolved ambiguity and never infer resolution from missing flags", () => {
  const refreshed = structuredClone(evidence);
  const journeyModel = refreshed.transformations.find(item => item.id === "p2-journey-and-route-variants-v1");
  const journey = journeyModel.journeys[0];
  journey.wafer_id = "SYN-REFRESH-010";
  journey.history_status = "INCOMPLETE";
  journey.history_flags = ["MATERIAL_MEMBERSHIP_AMBIGUOUS", "OBSERVATION_COVERAGE_INCOMPLETE"];
  journey.history_coverage = { coverage_evidence_level: "CONTRADICTORY" };
  journey.material_relationships = ["A", "B", "C"].map(suffix => ({
    record_id: `SYN-MEM-010-${suffix}`,
    source_id: "SYN_MATERIAL_EDGES",
    relationship_id: "SYN_REL_TIME_SCOPED_MEMBERSHIP",
  }));
  const summary = summarizeMembershipRefresh(refreshed, ["SYN-REFRESH-010"])[0];
  assert.match(summary, /membership remains ambiguous/);
  assert.match(summary, /CONTRADICTORY/);
  assert.match(summary, /SYN-MEM-010-A, SYN-MEM-010-B, SYN-MEM-010-C/);
  assert.match(summary, /SYN_MATERIAL_EDGES/);
  assert.match(summary, /SYN_REL_TIME_SCOPED_MEMBERSHIP/);

  journey.history_flags = ["OBSERVATION_COVERAGE_INCOMPLETE"];
  journey.material_relationships = [];
  const missing = summarizeMembershipRefresh(refreshed, ["SYN-REFRESH-010"])[0];
  assert.match(missing, /does not establish that the prior membership question is resolved/);
  assert.match(missing, /no material relationship records/);

  const absent = summarizeMembershipRefresh(refreshed, ["SYN-NOT-RETURNED"])[0];
  assert.match(absent, /previous membership question remains unresolved/);
});

test("P1 host adapters mount all five evidence panels with accessible tables and provenance drill-down", () => {
  const inspected = [];
  const mounted = mount({
    state: "ready",
    evidence,
    components: { Table: HostTable, JourneyTimeline: HostTimeline },
    onInspectEvidence: reference => inspected.push(reference),
    onExportEvidence: payload => assert.strictEqual(payload, evidence),
  });
  try {
    const { host } = mounted;
    for (const panel of ["journey", "exposure", "route", "counterevidence", "evidence"]) {
      assert.ok(host.querySelector(`[data-panel="${panel}"]`), `missing ${panel} panel`);
    }
    assert.ok(host.querySelector("[data-p1-journey-timeline]"));
    assert.match(host.textContent, /SYN-S4/);
    assert.match(host.textContent, /SYN_REL_WAFER_STEP/);
    assert.match(host.textContent, /normal_wafers_with_exact_exposure/);
    assert.match(host.textContent, /abnormal_wafers_verified_unexposed/);
    assert.match(host.textContent, /NOT_ESTABLISHED/);
    assert.match(host.textContent, /SYN_REL_WAFER_OUTCOME/);
    assert.match(host.textContent, /SYN_EXPOSURE_COVERAGE/);
    assert.match(host.textContent, /SYN_REL_ROUTE_DEFINITION/);
    assert.match(host.textContent, /ASSERTED_UNVERIFIED/);
    assert.match(host.textContent, /COVERAGE_INCOMPLETE/);
    assert.doesNotMatch(host.textContent, /EXPECTED_ROUTE_MISMATCH/);
    const tables = [...host.querySelectorAll("table")];
    assert.ok(tables.length >= 5);
    for (const table of tables) {
      assert.ok(table.querySelector("caption")?.textContent);
      assert.ok(table.querySelector("thead") && table.querySelector("tbody"));
      assert.ok([...table.querySelectorAll("th")].every(header => header.getAttribute("scope") === "col"));
    }
    const inspect = [...host.querySelectorAll("button")].find(button => button.textContent.startsWith("Inspect "));
    assert.ok(inspect);
    assert.equal(inspect.tabIndex, 0);
    act(() => inspect.click());
    assert.ok(inspected.length >= 1);
    assert.ok(inspected[0].sourceId || inspected[0].relationshipId);
    const exposureStep = [...host.querySelectorAll('[data-p1-table="Source-linked processing event exposure evidence"] button')]
      .find(button => button.textContent.includes("SYN-S1"));
    assert.ok(exposureStep, "an exact exposure row must expose its step-instance identity");
    act(() => exposureStep.click());
    assert.ok(inspected.some(reference => reference.recordId === "SYN-S1"
      && reference.relationshipId === "SYN_REL_WAFER_STEP"));
    const routeInspector = [...host.querySelectorAll('[data-panel="route"] button')]
      .find(button => button.textContent.includes("SYN_ROUTE_DEFINITIONS"));
    assert.ok(routeInspector, "route definition provenance should be inspectable from the route panel");
    act(() => routeInspector.click());
    assert.ok(inspected.some(reference => reference.sourceId === "SYN_ROUTE_DEFINITIONS"
      && reference.relationshipId === "SYN_REL_ROUTE_DEFINITION"));
    const exportButton = [...host.querySelectorAll("button")].find(button => button.textContent.includes("Export reproducible evidence"));
    assert.ok(exportButton);
    act(() => exportButton.click());
  } finally {
    mounted.unmount();
  }
});

test("the headless fallback remains keyboard and table accessible when P1 adapters are not injected", () => {
  const mounted = mount({ state: "ready", evidence });
  try {
    const { host } = mounted;
    assert.equal(host.querySelectorAll("[data-panel]").length, 5);
    assert.ok(host.querySelector('[aria-label="Chronological wafer journey timeline"] ol'));
    const tables = [...host.querySelectorAll("table")];
    assert.ok(tables.length >= 5);
    for (const table of tables) {
      const columns = table.querySelectorAll("thead th").length;
      assert.ok(columns > 0);
      assert.ok([...table.querySelectorAll("thead th")].every(header => header.getAttribute("scope") === "col"));
      for (const row of table.querySelectorAll("tbody tr")) {
        const cells = row.querySelectorAll("td");
        assert.ok(cells.length === columns || (cells.length === 1 && Number(cells[0].getAttribute("colspan")) === columns));
      }
    }
  } finally {
    mounted.unmount();
  }
});

test("React journey chronology surfaces conflicting lot evidence and the material record", () => {
  const conflicted = structuredClone(evidence);
  const journey = conflicted.transformations.find(item => item.id === "p2-journey-and-route-variants-v1").journeys[0];
  const step = journey.steps[0];
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
  const mounted = mount({ state: "ready", evidence: conflicted });
  try {
    const search = mounted.host.querySelector("#p2-journey-filter");
    assert.ok(search, "journey filter must be keyboard-addressable");
    act(() => {
      Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, "value").set.call(search, journey.wafer_id);
      search.dispatchEvent(new dom.window.Event("input", { bubbles: true }));
    });
    assert.match(mounted.host.querySelector('[data-panel="journey"]').textContent, /1 matching wafer journey/);
    const table = mounted.host.querySelector('[aria-label="Chronological process step instances"] table');
    assert.ok(table);
    const headers = [...table.querySelectorAll("thead th")].map(item => item.textContent);
    const lotColumn = headers.indexOf("Lot evidence at event");
    assert.notEqual(lotColumn, -1);
    assert.equal(table.querySelector("tbody tr").cells[lotColumn].textContent,
      "CONFLICT · event row LOT-A; time-scoped membership LOT-B · membership record MEM-LOT-B");
  } finally {
    mounted.unmount();
  }
});

test("large fallback histories page journey and table rows without dropping export evidence", () => {
  const expanded = expandJourneyEvidence(30, 4);
  const mounted = mount({ state: "ready", evidence: expanded, onExportEvidence: value => assert.strictEqual(value, expanded) });
  try {
    const { host } = mounted;
    const journeyControls = host.querySelector('[aria-label="Journey page controls"]');
    assert.equal(journeyControls.tagName, "NAV");
    assert.match(journeyControls.textContent, /Showing journeys 1–25 of 30/);
    assert.equal(host.querySelectorAll('[aria-label^="Wafer "] ol li').length, 100);
    const nextJourney = [...journeyControls.querySelectorAll("button")].find(button => button.textContent === "Next journeys");
    assert.equal(nextJourney.tabIndex, 0);
    act(() => nextJourney.click());
    assert.match(journeyControls.textContent, /Showing journeys 26–30 of 30/);
    assert.equal(host.querySelectorAll('[aria-label^="Wafer "] ol li').length, 20);

    const tableControls = host.querySelector('[aria-label="Page controls for Chronological process step instances"]');
    assert.equal(tableControls.tagName, "NAV");
    assert.match(tableControls.textContent, /Rows 1–100 of 120/);
    act(() => [...tableControls.querySelectorAll("button")].find(button => button.textContent === "Next rows").click());
    assert.match(tableControls.textContent, /Rows 101–120 of 120/);
    const journeyTable = host.querySelector('[role="region"][aria-label="Chronological process step instances"] table');
    assert.equal(journeyTable.querySelectorAll("tbody tr").length, 20);

    const exportButton = [...host.querySelectorAll("button")].find(button => button.textContent.includes("Export reproducible evidence"));
    assert.ok(exportButton);
    act(() => exportButton.click());
  } finally {
    mounted.unmount();
  }
});

test("large route variants summarize member IDs and preserve the full set in collapsed evidence details", () => {
  const expanded = expandJourneyEvidence(30, 2);
  const journey = expanded.transformations.find(item => item.id === "p2-journey-and-route-variants-v1");
  const memberIds = journey.journeys.map(item => item.wafer_id);
  journey.route_variants = [{
    count: memberIds.length,
    operations: ["ETCH", "CLEAN"],
    order_status: "ORDERED",
    route_id_sequence: ["SYN-ROUTE"],
    route_version_sequence: ["v1"],
    share_of_ordered_observed_histories: 1,
    ordered_observed_history_denominator: memberIds.length,
    wafer_ids: memberIds,
  }];
  const mounted = mount({ state: "ready", evidence: expanded });
  try {
    const { host } = mounted;
    const routeTable = host.querySelector('[data-panel="route"] table');
    const memberCell = routeTable.querySelector("tbody tr td");
    assert.match(memberCell.textContent, /30 wafer\(s\) · sample SYN-PAGE-W1, SYN-PAGE-W2/);
    assert.doesNotMatch(memberCell.textContent, /SYN-PAGE-W30/);
    const membership = [...host.querySelectorAll('[data-panel="route"] details')]
      .find(item => item.querySelector("summary")?.textContent === "Complete route-variant wafer membership sets");
    assert.ok(membership);
    assert.equal(membership.open, false);
    const fullEvidence = JSON.parse(membership.querySelector("pre").textContent);
    assert.equal(fullEvidence[0].wafer_ids.length, 30);
    assert.deepEqual(fullEvidence[0].wafer_ids, memberIds);
  } finally {
    mounted.unmount();
  }
});

test("host request controls delegate cancel, retry, and new investigation actions", () => {
  const actions = [];
  const mounted = mount({
    state: "loading",
    evidence,
    onCancel: () => actions.push("cancel"),
    onRetry: () => actions.push("retry"),
    onStartInvestigation: () => actions.push("start"),
  });
  try {
    const { host } = mounted;
    assert.equal(host.querySelectorAll("[data-panel]").length, 0);
    assert.doesNotMatch(host.textContent, /SYN-W1/);
    assert.equal([...host.querySelectorAll("button")].some(button => button.textContent.includes("Export reproducible evidence")), false);
    const cancel = [...host.querySelectorAll("button")].find(button => button.textContent === "Cancel investigation");
    const start = [...host.querySelectorAll("button")].find(button => button.textContent === "Start or change investigation");
    assert.ok(cancel && start);
    act(() => { cancel.click(); start.click(); });
    act(() => mounted.root.render(React.createElement(P2ProcessForensicsPanels, {
      state: "cancelled", onRetry: () => actions.push("retry"),
    })));
    const retry = [...host.querySelectorAll("button")].find(button => button.textContent === "Retry investigation");
    assert.ok(retry);
    act(() => retry.click());
    assert.deepEqual(actions, ["cancel", "start", "retry"]);
    assert.match(host.textContent, /No partial evidence is displayed/);
  } finally {
    mounted.unmount();
  }
});

test("empty, error, and refused states stay explicit and never assert a cause", () => {
  const mounted = mount({ state: "idle" });
  try {
    assert.match(mounted.host.textContent, /Select an abnormal wafer or lot/);
    act(() => mounted.root.render(React.createElement(P2ProcessForensicsPanels, { state: "error", errorMessage: "Fixture denied" })));
    assert.match(mounted.host.textContent, /Fixture denied/);
    assert.ok(mounted.host.querySelector('[role="alert"]'));
    const refused = structuredClone(evidence);
    refused.status = "REFUSED";
    refused.claims = structuredClone(evidence.claims);
    refused.limitations = ["No approved read permission was supplied."];
    act(() => mounted.root.render(React.createElement(P2ProcessForensicsPanels, { state: "ready", evidence: refused })));
    assert.match(mounted.host.textContent, /This investigation was refused/);
    assert.match(mounted.host.textContent, /No approved read permission/);
    assert.match(mounted.host.textContent, /No route, exposure, or hypothesis findings are displayed/);
    assert.equal(mounted.host.querySelector('[data-panel="journey"]'), null);
    assert.doesNotMatch(mounted.host.textContent, /SYN-W1/);
    assert.doesNotMatch(mounted.host.textContent, /cause established/i);
    assert.match(mounted.host.textContent, /Synthetic demonstration evidence/);
    const errorEnvelope = structuredClone(evidence);
    errorEnvelope.status = "ERROR";
    act(() => mounted.root.render(React.createElement(P2ProcessForensicsPanels, { state: "ready", evidence: errorEnvelope })));
    assert.match(mounted.host.textContent, /No findings are displayed/);
    assert.equal(mounted.host.querySelector('[data-panel="exposure"]'), null);
  } finally {
    mounted.unmount();
  }
});

test("invalid contract envelopes are rejected before rendering", () => {
  assert.throws(() => buildP2PanelModels({ ...evidence, product_id: "p1" }), /contract-v1 P2 evidence envelope/);
  assert.throws(() => buildP2PanelModels({ ...evidence, provenance: {} }), /contract-v1 P2 evidence envelope/);
});
