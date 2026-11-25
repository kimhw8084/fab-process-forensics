import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { performance } from "node:perf_hooks";
import { JSDOM } from "../ui/p2-react/node_modules/jsdom/lib/api.js";
import React from "../ui/p2-react/node_modules/react/index.js";
import { createRoot } from "../ui/p2-react/node_modules/react-dom/client.js";
import { P2ProcessForensicsPanels } from "../ui/p2-react/dist/index.js";

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const sourceEvidence = JSON.parse(fs.readFileSync(path.join(rootDir, "qualification/evidence/mcp-end-to-end-workflow.json"), "utf8"));
const journeyModel = sourceEvidence.transformations.find(item => item.id === "p2-journey-and-route-variants-v1");
const journeyTemplate = journeyModel.journeys[0];
const stepTemplate = journeyTemplate.steps;

function makeEvidence(waferCount, stepsPerWafer) {
  const evidence = structuredClone(sourceEvidence);
  const journey = evidence.transformations.find(item => item.id === "p2-journey-and-route-variants-v1");
  const journeys = [];
  for (let waferIndex = 0; waferIndex < waferCount; waferIndex += 1) {
    const template = journeyModel.journeys[waferIndex % journeyModel.journeys.length];
    const steps = Array.from({ length: stepsPerWafer }, (_, stepIndex) => {
      const sourceStep = template.steps[stepIndex % template.steps.length] ?? stepTemplate[0];
      const eventTime = new Date(Date.UTC(2026, 10, 21, 0, 0) + (waferIndex * stepsPerWafer + stepIndex) * 60_000).toISOString();
      return {
        ...structuredClone(sourceStep),
        wafer_id: `P2-BENCH-W${String(waferIndex + 1).padStart(5, "0")}`,
        step_instance_id: `P2-BENCH-W${String(waferIndex + 1).padStart(5, "0")}-S${String(stepIndex + 1).padStart(3, "0")}`,
        timestamp: eventTime,
        timestamp_utc: eventTime,
        recorded_at: new Date(Date.parse(eventTime) + 120_000).toISOString(),
      };
    });
    const stepIds = steps.map(step => step.step_instance_id);
    const routeSegments = (template.route_segments ?? []).map(segment => ({
      ...structuredClone(segment),
      step_instance_ids: stepIds,
      process_step_evidence: steps.map(step => ({
        wafer_id: step.wafer_id,
        step_instance_id: step.step_instance_id,
        source_id: step.source_id,
        relationship_id: step.relationship_id,
        timestamp_utc: step.timestamp_utc,
      })),
    }));
    journeys.push({
      ...structuredClone(template),
      wafer_id: `P2-BENCH-W${String(waferIndex + 1).padStart(5, "0")}`,
      steps,
      route_segments: routeSegments,
      rework_edges: [],
    });
  }
  journey.journeys = journeys;
  journey.route_variants = journeyModel.route_variants.map((variant, variantIndex) => {
    const waferIds = journeys.filter((_, index) => index % journeyModel.route_variants.length === variantIndex).map(item => item.wafer_id);
    return {
      ...structuredClone(variant),
      count: waferIds.length,
      wafer_ids: waferIds,
      ordered_observed_history_denominator: waferCount,
      share_of_ordered_observed_histories: waferIds.length / waferCount,
    };
  });
  journey.route_population_summary = {
    ...journey.route_population_summary,
    observed_event_histories: waferCount,
    ordered_observed_history_denominator: waferCount,
  };
  evidence.provenance.input_sha256 = "0".repeat(64);
  return evidence;
}

const dom = new JSDOM("<!doctype html><html><body><div id=app></div></body></html>", { url: "http://localhost/" });
globalThis.window = dom.window;
globalThis.document = dom.window.document;
globalThis.HTMLElement = dom.window.HTMLElement;
globalThis.Node = dom.window.Node;
Object.defineProperty(globalThis, "navigator", { configurable: true, value: dom.window.navigator });
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const { act } = React;
const host = document.querySelector("#app");
const root = createRoot(host);
const results = [];
for (const waferCount of [100, 500, 1000]) {
  const stepsPerWafer = 8;
  const evidence = makeEvidence(waferCount, stepsPerWafer);
  globalThis.gc?.();
  const heapBefore = process.memoryUsage().heapUsed;
  const start = performance.now();
  act(() => root.render(React.createElement(P2ProcessForensicsPanels, { state: "ready", evidence })));
  const renderMs = performance.now() - start;
  const tableRows = host.querySelectorAll("tbody tr").length;
  const journeySteps = host.querySelectorAll('[aria-label^="Wafer "] ol li').length;
  const inputStepInstances = waferCount * stepsPerWafer;
  const expectedVisibleJourneys = Math.min(waferCount, 25);
  assert.equal(journeySteps, expectedVisibleJourneys * stepsPerWafer);
  assert.ok(tableRows < 300, `fallback rendering mounted ${tableRows} table rows for ${waferCount} wafers`);
  results.push({
    synthetic_wafers: waferCount,
    input_step_instances: inputStepInstances,
    rendered_timeline_step_instances: journeySteps,
    rendered_table_rows: tableRows,
    render_ms: Number(renderMs.toFixed(2)),
    heap_delta_bytes: process.memoryUsage().heapUsed - heapBefore,
    html_bytes: Buffer.byteLength(host.innerHTML),
    render_basis: "P2 React module + JSDOM DOM reconciliation; not a native browser benchmark",
  });
  act(() => root.render(React.createElement("div")));
}
act(() => root.unmount());
dom.window.close();
console.log(JSON.stringify({
  status: "PASS_P2_REACT_SYNTHETIC_RENDER_PROXY",
  p2_module_version: "1.0.0",
  scenarios: results,
  limitations: ["Rows are synthetic repetitions derived from source-linked fixture shapes.", "JSDOM timing is not a native browser or target-device performance result.", "The benchmark measures panel rendering, not MCP retrieval or analysis execution."],
}, null, 2));
