import { Fragment, useEffect, useState } from "react";
import { buildP2PanelModels } from "./model.js";
import type {
  JsonRecord,
  P2EvidenceEnvelope,
  P2EvidenceReference,
  P2Journey,
  P2PanelModels,
  P2ProcessForensicsProps,
  P2ProcessStep,
  P2TableProps,
  P2TableRow,
} from "./types.js";

export { buildP2PanelModels, summarizeMembershipRefresh } from "./model.js";
export type * from "./types.js";

const asText = (value: unknown, fallback = "Unknown"): string =>
  typeof value === "string" || typeof value === "number" ? String(value) : fallback;

const asRecords = (value: unknown): JsonRecord[] =>
  Array.isArray(value) ? value.filter((item): item is JsonRecord => item !== null && typeof item === "object" && !Array.isArray(item)) : [];
const TABLE_PAGE_SIZE = 100;
const JOURNEY_PAGE_SIZE = 25;

const compact = (value: readonly (string | null | undefined)[]): string => value.filter(Boolean).join(" / ") || "Unknown";

function lotEvidenceAtEvent(step: P2ProcessStep): string {
  const eventLot = asText(step.lot_id_at_event);
  const state = step.membership_state;
  if (state !== "CONFLICTS_WITH_EVENT_ROW_LOT_ID") {
    if (!state) return eventLot;
    const label = state === "SOURCE_LINKED_TIME_SCOPED_MEMBERSHIP"
      ? "source-linked membership"
      : state.replaceAll("_", " ").toLowerCase();
    return `${eventLot} · ${label}`;
  }

  const lineage = asRecords([step.lot_lineage])[0];
  const conflicts = asRecords(lineage?.missing_evidence).filter(item =>
    item.reason === "EVENT_LOT_ID_CONFLICTS_WITH_TIME_SCOPED_MEMBERSHIP",
  );
  const candidateLots = [...new Set(conflicts.flatMap(item =>
    Array.isArray(item.candidate_lot_ids) ? item.candidate_lot_ids.filter((value): value is string => typeof value === "string") : [],
  ))];
  const membershipRecords = [...new Set(asRecords(lineage?.seeds).flatMap(seed => asRecords(seed.provenance))
    .map(item => item.material_relationship_id).filter((value): value is string => typeof value === "string"))];
  const membership = candidateLots.join(", ") || "unresolved";
  const records = membershipRecords.length ? ` · membership record ${membershipRecords.join(", ")}` : "";
  return `CONFLICT · event row ${eventLot}; time-scoped membership ${membership}${records}`;
}

const evidenceRef = (record: JsonRecord): P2EvidenceReference | undefined => {
  const sourceId = typeof record.source_id === "string" ? record.source_id : undefined;
  const relationshipId = typeof record.relationship_id === "string" ? record.relationship_id : undefined;
  const recordId = typeof record.record_id === "string" ? record.record_id
    : typeof record.step_instance_id === "string" ? record.step_instance_id
      : typeof record.outcome_id === "string" ? record.outcome_id : undefined;
  return sourceId || relationshipId || recordId
    ? { ...(sourceId ? { sourceId } : {}), ...(relationshipId ? { relationshipId } : {}), ...(recordId ? { recordId } : {}) }
    : undefined;
};

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "Unknown";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value, null, 2) ?? "Unknown";
}

function DefaultTable({ caption, columns, rows, onInspectEvidence }: P2TableProps) {
  const hasEvidenceColumn = columns.includes("Evidence inspector");
  const [page, setPage] = useState(0);
  useEffect(() => setPage(0), [caption, rows.length]);
  const pageCount = Math.max(1, Math.ceil(rows.length / TABLE_PAGE_SIZE));
  const currentPage = Math.min(page, pageCount - 1);
  const visibleRows = rows.slice(currentPage * TABLE_PAGE_SIZE, (currentPage + 1) * TABLE_PAGE_SIZE);
  const firstVisibleRow = rows.length ? currentPage * TABLE_PAGE_SIZE + 1 : 0;
  const lastVisibleRow = Math.min((currentPage + 1) * TABLE_PAGE_SIZE, rows.length);
  return (
    <div className="p2-paged-table">
      {rows.length > TABLE_PAGE_SIZE ? <nav className="p2-page-controls" aria-label={`Page controls for ${caption}`}>
        <span aria-live="polite">Rows {firstVisibleRow}–{lastVisibleRow} of {rows.length}</span>
        <button type="button" disabled={currentPage === 0} onClick={() => setPage(Math.max(0, currentPage - 1))}>Previous rows</button>
        <button type="button" disabled={currentPage + 1 >= pageCount} onClick={() => setPage(Math.min(pageCount - 1, currentPage + 1))}>Next rows</button>
      </nav> : null}
      <div className="p2-table-scroll" role="region" aria-label={caption} tabIndex={0}>
        <table>
          <caption>{caption}</caption>
          <thead><tr>{columns.map(column => <th key={column} scope="col">{column}</th>)}</tr></thead>
          <tbody>
            {visibleRows.length ? visibleRows.map(row => (
              <tr key={row.id}>
                {row.cells.map((cell, index) => <td key={`${row.id}-${index}`}>{cell}</td>)}
                {hasEvidenceColumn ? <td>
                  {row.evidenceRefs?.length ? row.evidenceRefs.map((reference, index) => {
                    const label = [reference.recordId, reference.sourceId, reference.relationshipId].filter(Boolean).join(" · ");
                    return onInspectEvidence
                      ? <Fragment key={`${row.id}-ref-${index}`}><button type="button" onClick={() => onInspectEvidence(reference)}>Inspect {label || "evidence"}</button>{index + 1 < (row.evidenceRefs?.length ?? 0) ? " " : ""}</Fragment>
                      : <span key={`${row.id}-ref-${index}`}>{label || "Evidence reference"}</span>;
                  }) : "No linked provenance"}
                </td> : null}
              </tr>
            )) : <tr><td colSpan={columns.length}>No records are available.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Details({ title, value }: { readonly title: string; readonly value: unknown }) {
  return <details><summary>{title}</summary><pre>{formatValue(value)}</pre></details>;
}

function DefaultTimeline({ journeys }: { readonly journeys: readonly P2Journey[] }) {
  return <div aria-label="Chronological wafer journey timeline">
    {journeys.map(journey => (
      <section key={journey.wafer_id} aria-label={`Wafer ${journey.wafer_id} chronology`}>
        <h3>Wafer {journey.wafer_id} · {journey.history_status.replaceAll("_", " ")}</h3>
        <ol>
          {journey.steps.map(step => (
            <li key={step.step_instance_id}>
              <time>{asText(step.timestamp)}</time> — {asText(step.operation)} ({step.step_instance_id})
              {step.time_uncertainty_seconds ? ` · ±${step.time_uncertainty_seconds}s` : ""}
              {step.order_uncertain_with?.length ? ` · order uncertain with ${step.order_uncertain_with.join(", ")}` : ""}
            </li>
          ))}
        </ol>
      </section>
    ))}
  </div>;
}

function makeTable(
  id: string,
  caption: string,
  columns: readonly string[],
  rows: readonly (readonly string[])[],
  refs: readonly (P2EvidenceReference | readonly P2EvidenceReference[] | undefined)[] = [],
): P2TableProps {
  return {
    caption,
    columns,
    rows: rows.map((cells, index) => ({
      id: `${id}-${index}`,
      cells,
      ...(refs[index] ? { evidenceRefs: Array.isArray(refs[index]) ? refs[index] as readonly P2EvidenceReference[] : [refs[index] as P2EvidenceReference] } : {}),
    })),
  };
}

function routeRows(journeys: readonly P2Journey[]) {
  return journeys.flatMap(journey => journey.steps.map((step: P2ProcessStep) => [
    journey.wafer_id,
    step.step_instance_id,
    compact([step.route_id, step.route_version]),
    asText(step.operation),
    asText(step.operation_definition_id ?? step.operation_definition_status),
    journey.route_conformance.replaceAll("_", " "),
  ]));
}

function routeRefs(journeys: readonly P2Journey[]) {
  return journeys.flatMap(journey => journey.steps.map(step => {
    const segment = journey.route_segments?.find(item =>
      Array.isArray(item.step_instance_ids) && item.step_instance_ids.includes(step.step_instance_id),
    );
    const definitionRef = segment?.approved_route_source_id && segment.approved_route_relationship_id
      ? { sourceId: String(segment.approved_route_source_id), relationshipId: String(segment.approved_route_relationship_id) }
      : undefined;
    return [evidenceRef(step), definitionRef].filter((ref): ref is P2EvidenceReference => Boolean(ref));
  }));
}

function journeyEvidenceRefs(journey: P2Journey): P2EvidenceReference[] {
  const refs = journey.steps.map(step => evidenceRef(step)).filter((ref): ref is P2EvidenceReference => Boolean(ref));
  for (const segment of journey.route_segments ?? []) {
    if (segment.approved_route_source_id && segment.approved_route_relationship_id) {
      refs.push({ sourceId: String(segment.approved_route_source_id), relationshipId: String(segment.approved_route_relationship_id) });
    }
  }
  return refs.filter((ref, index) => refs.findIndex(item =>
    item.sourceId === ref.sourceId && item.relationshipId === ref.relationshipId && item.recordId === ref.recordId,
  ) === index);
}

function routeVariantRefs(variants: readonly { readonly wafer_ids: readonly string[] }[], journeys: readonly P2Journey[]) {
  return variants.map(variant => journeys
    .filter(journey => variant.wafer_ids.includes(journey.wafer_id))
    .flatMap(journey => journeyEvidenceRefs(journey)));
}

function routeVariantTable(models: P2PanelModels): P2TableProps {
  const variants = models.journey.route_variants;
  return makeTable("route", "Observed route variants with declared denominator", ["Wafers (count and sample)", "Observed operation sequence", "Order status", "Route versions", "Share of ordered observed histories", "Denominator", "Evidence inspector"], variants.map(variant => [
    `${variant.count} wafer(s)${variant.wafer_ids.length ? ` · sample ${variant.wafer_ids.slice(0, 6).join(", ")}${variant.wafer_ids.length > 6 ? " …" : ""}` : ""}`, variant.operations.join(" → "), variant.order_status,
    compact([...(variant.route_id_sequence ?? []), ...(variant.route_version_sequence ?? [])]),
    typeof variant.share_of_ordered_observed_histories === "number" ? `${(variant.share_of_ordered_observed_histories * 100).toFixed(1)}%` : "Not computed",
    typeof variant.ordered_observed_history_denominator === "number" ? String(variant.ordered_observed_history_denominator) : "Not supplied",
  ]), routeVariantRefs(variants, models.journey.journeys));
}

export function P2ProcessForensicsPanels(props: P2ProcessForensicsProps) {
  const { state, evidence, components, onInspectEvidence, className } = props;
  const currentEvidence = state === "ready" ? evidence : undefined;
  const Table = components?.Table ?? DefaultTable;
  const models = currentEvidence ? buildP2PanelModels(currentEvidence) : null;
  const [journeyPage, setJourneyPage] = useState(0);
  const [journeyFilter, setJourneyFilter] = useState("");
  useEffect(() => {
    setJourneyPage(0);
    setJourneyFilter("");
  }, [models?.summary.investigation_id]);
  const query = journeyFilter.trim().toLowerCase();
  const matchingJourneys = models?.journey.journeys.filter(journey => !query || [
    journey.wafer_id,
    ...journey.steps.flatMap(step => [step.step_instance_id, step.operation, step.lot_id, step.route_id, step.route_version]),
    ...(journey.material_relationships ?? []).flatMap(item => [item.record_id, item.relationship_type]),
  ].some(value => typeof value === "string" && value.toLowerCase().includes(query))) ?? [];
  const journeyCount = matchingJourneys.length;
  const journeyPageCount = Math.max(1, Math.ceil(journeyCount / JOURNEY_PAGE_SIZE));
  const currentJourneyPage = Math.min(journeyPage, journeyPageCount - 1);
  const journeyStart = currentJourneyPage * JOURNEY_PAGE_SIZE;
  const visibleJourneys = matchingJourneys.slice(journeyStart, journeyStart + JOURNEY_PAGE_SIZE);
  const suppressFindings = models?.summary.status === "REFUSED" || models?.summary.status === "ERROR";
  const table = (tableProps: P2TableProps) => <Table {...tableProps} {...(onInspectEvidence ? { onInspectEvidence } : {})} />;
  const panelProps = className ? { className } : {};
  const statusText = currentEvidence ? `${currentEvidence.status} · ${currentEvidence.mode}` : state.toUpperCase();
  const journeyTable = makeTable("journey", "Chronological process step instances", ["Wafer", "Step instance", "Operation", "Event time / uncertainty", "Recorded time", "Lot evidence at event", "Tool / chamber", "Operation definition", "History / route state", "Evidence inspector"],
    matchingJourneys.flatMap(journey => journey.steps.map(step => [
      journey.wafer_id, step.step_instance_id, asText(step.operation),
      `${asText(step.timestamp)}${step.time_uncertainty_seconds ? ` · ±${step.time_uncertainty_seconds}s` : ""}${step.order_uncertain_with?.length ? ` · unordered with ${step.order_uncertain_with.join(", ")}` : ""}`,
      asText(step.recorded_at), lotEvidenceAtEvent(step), compact([step.tool_id, step.chamber_id]),
      asText(step.operation_definition_id ?? step.operation_definition_status),
      `${journey.history_status} / ${journey.route_conformance}`,
    ])), matchingJourneys.flatMap(journey => journey.steps.map(step => evidenceRef(step))));

  return (
    <div {...panelProps} data-p2-module="1.0.0" aria-label="FAB Process Forensics">
      <header>
        <h2>FAB Process Forensics</h2>
        <p role={state === "error" || currentEvidence?.status === "REFUSED" || currentEvidence?.status === "ERROR" ? "alert" : "status"} aria-live="polite">
          {statusText}{currentEvidence ? ` · Investigation ${currentEvidence.investigation_id}` : ""}
        </p>
        {currentEvidence?.mode === "SYNTHETIC_DEMO" ? <p role="note">Synthetic demonstration evidence. It does not establish company source approval.</p> : null}
        {state === "loading" && props.onCancel ? <button type="button" onClick={props.onCancel}>Cancel investigation</button> : null}
        {(state === "error" || state === "cancelled") && props.onRetry ? <button type="button" onClick={props.onRetry}>Retry investigation</button> : null}
        {props.onStartInvestigation ? <button type="button" onClick={props.onStartInvestigation}>Start or change investigation</button> : null}
        {currentEvidence && props.onExportEvidence ? <button type="button" onClick={() => props.onExportEvidence?.(currentEvidence)}>Export reproducible evidence</button> : null}
        {state === "error" ? <p role="alert">{props.errorMessage || "The host could not complete this investigation."}</p> : null}
        {state === "cancelled" ? <p role="status">Investigation cancelled. No partial evidence is displayed.</p> : null}
        {currentEvidence?.status === "ERROR" ? <p role="alert">The evidence envelope reports an analysis error. No findings are displayed.</p> : null}
        {!evidence && state === "idle" ? <p>Select an abnormal wafer or lot, or a suspected equipment interval, in the host to begin.</p> : null}
        {!evidence && state === "ready" ? <p role="status">The host returned no evidence envelope.</p> : null}
        {currentEvidence?.status === "REFUSED" ? <p role="alert">This investigation was refused. Review the stated limitations and source permissions with the host before retrying.</p> : null}
      </header>

      {models ? suppressFindings ? <section data-panel="evidence" aria-labelledby="p2-unavailable-title">
        <h2 id="p2-unavailable-title">Analysis findings withheld</h2>
        <p>{models.summary.status === "REFUSED" ? "The analysis was refused. No route, exposure, or hypothesis findings are displayed." : "The analysis returned an error. No route, exposure, or hypothesis findings are displayed."}</p>
        {models.summary.limitations.length ? <ul>{models.summary.limitations.map((item, index) => <li key={`refusal-limitation-${index}`}>{item}</li>)}</ul> : <p>No additional reason was supplied.</p>}
        <p>Evidence hash: <code>{models.evidence.input_sha256}</code></p>
      </section> : <>
        <section data-panel="journey" aria-labelledby="p2-journey-title">
          <h2 id="p2-journey-title">Wafer and lot journey</h2>
          {models.journey.journeys.length ? <>
            <label htmlFor="p2-journey-filter">Find a wafer, lot, step instance, or operation</label>
            <input id="p2-journey-filter" type="search" value={journeyFilter}
              onChange={event => { setJourneyFilter(event.currentTarget.value); setJourneyPage(0); }}
              aria-label="Find a wafer, lot, step instance, or operation" />
            {journeyCount > JOURNEY_PAGE_SIZE ? <nav className="p2-page-controls" aria-label="Journey page controls">
              <span aria-live="polite">Showing journeys {journeyStart + 1}–{Math.min(journeyStart + JOURNEY_PAGE_SIZE, journeyCount)} of {journeyCount}</span>
              <button type="button" disabled={currentJourneyPage === 0} onClick={() => setJourneyPage(Math.max(0, currentJourneyPage - 1))}>Previous journeys</button>
              <button type="button" disabled={currentJourneyPage + 1 >= journeyPageCount} onClick={() => setJourneyPage(Math.min(journeyPageCount - 1, currentJourneyPage + 1))}>Next journeys</button>
            </nav> : <p role="status">Showing {journeyCount} matching wafer journey{journeyCount === 1 ? "" : "s"}.</p>}
            {journeyCount ? (components?.JourneyTimeline
              ? <components.JourneyTimeline journeys={visibleJourneys} {...(onInspectEvidence ? { onInspectEvidence } : {})} />
              : <DefaultTimeline journeys={visibleJourneys} />)
              : <p role="status">No wafer or lot journey matches this search.</p>}
            {journeyCount ? table(journeyTable) : null}
            {visibleJourneys.map(journey => <details key={`${journey.wafer_id}-lineage`}>
              <summary>Inspect {journey.wafer_id} lineage, membership, route segments, and rework</summary>
              <p>History: {journey.history_status}. Route conformance: {journey.route_conformance}.</p>
              <Details title="History coverage" value={journey.history_coverage ?? { status: "COVERAGE_UNKNOWN" }} />
              <Details title="Time-scoped lot membership and lineage paths" value={journey.lot_lineage_paths ?? []} />
              <Details title="Material relationships and provenance" value={journey.material_relationships ?? []} />
              <Details title="Route segments and explicit rework edges" value={{ route_segments: journey.route_segments ?? [], rework_edges: journey.rework_edges ?? [] }} />
            </details>)}
          </> : <p>No journey was produced. Missing event history is not interpreted as an empty manufacturing path.</p>}
        </section>

        <section data-panel="exposure" aria-labelledby="p2-exposure-title">
          <h2 id="p2-exposure-title">Exposure evidence and comparator populations</h2>
          {models.exposure.populations.length
            ? table(makeTable("population", "Exposure classification and evidence basis", ["Classification", "Wafer count", "Wafer IDs", "Basis"], models.exposure.populations.map(population => [population.classification, String(population.count), population.wafer_ids.join(", ") || "None", population.basis])))
            : <p>No source-backed exposure populations were supplied.</p>}
          {models.exposure.analysis ? <>
            <p>{asText(models.exposure.analysis.scope_type)} {asText(models.exposure.analysis.scope_id)} · {formatValue(models.exposure.analysis.window)}</p>
            <p>Coverage evidence level: <strong>{asText(models.exposure.analysis.coverage_evidence_level, "UNKNOWN")}</strong>. Only SOURCE_VERIFIED coverage supports an observed-unexposed comparator. {asText(models.exposure.analysis.coverage_reason, "Coverage status not supplied.")}</p>
            <p>Condition-event timing is contextual evidence. Time overlap alone does not establish processing exposure or cause.</p>
            {table(makeTable("exposure", "Source-linked processing event exposure evidence", ["Wafer", "Step instance", "Classification", "Event time", "Exact scope", "Source relationship", "Evidence inspector"], asRecords(models.exposure.analysis.evidence).map(row => [
              asText(row.wafer_id), asText(row.step_instance_id), asText(row.classification), asText(row.timestamp_utc ?? row.timestamp), compact([asText(row.scope_type, ""), asText(row.scope_id, "")]), compact([asText(row.source_id, ""), asText(row.relationship_id, "")]),
            ]), asRecords(models.exposure.analysis.evidence).map(row => evidenceRef(row))))}
            <Details title="Coverage scope, authority claim, maintenance context, and uncertainty" value={{ coverage: models.exposure.analysis.coverage_evidence ?? {}, asserted_nonmatches: models.exposure.analysis.not_observed_exposed_under_unverified_coverage ?? [], condition_event_status: models.exposure.analysis.condition_event_status, condition_events: models.exposure.analysis.condition_event_evidence ?? [], uncertainty: evidence?.uncertainty ?? {} }} />
          </> : null}
        </section>

        <section data-panel="route" aria-labelledby="p2-route-title">
          <h2 id="p2-route-title">Route variants and conformance</h2>
          {models.journey.route_variants.length
            ? table(routeVariantTable(models))
            : <p>No ordered observed route variants are available.</p>}
          {models.journey.route_variants.length ? <Details title="Complete route-variant wafer membership sets" value={models.journey.route_variants.map(variant => ({
            operations: variant.operations,
            route_ids: variant.route_id_sequence ?? [],
            route_versions: variant.route_version_sequence ?? [],
            order_status: variant.order_status,
            wafer_ids: variant.wafer_ids,
            denominator: variant.ordered_observed_history_denominator ?? null,
          }))} /> : null}
          {models.journey.route_population_summary ? <Details title="Route coverage and population denominator" value={models.journey.route_population_summary} /> : null}
          <p>Route conformance is asserted only against a verified, effective route definition and adequate history coverage. Incomplete histories remain unknown.</p>
          {table(makeTable("route-conformance", "Actual step instances and route state", ["Wafer", "Step instance", "Route / version", "Actual operation", "Definition", "Conformance", "Evidence inspector"], routeRows(models.journey.journeys), routeRefs(models.journey.journeys)))}
        </section>

        <section data-panel="counterevidence" aria-labelledby="p2-counter-title">
          <h2 id="p2-counter-title">Competing hypotheses and counterevidence</h2>
          {models.counterevidence.investigations.length ? models.counterevidence.investigations.map((item, index) => <article key={`hypothesis-${index}`}>
            <h3>{asText(item.question, "Investigation hypothesis")}</h3>
            <p>{asText(item.interpretation, "Interpretation unavailable.")}</p>
            <p>Statistical association: {formatValue(item.statistical_association)}. Proposed explanation: {formatValue(item.proposed_explanation)}. Causal conclusion: {formatValue(item.causal_conclusion)}.</p>
            <Details title="Supporting and contradicting observations" value={{ supporting: item.supporting_observations ?? [], contradicting: item.contradicting_observations ?? {} }} />
            <Details title="Shared exposure, verified nonmatches, and asserted nonmatches" value={{ normal_wafers_with_exact_exposure: item.normal_wafers_with_exact_exposure ?? [], abnormal_wafers_without_observed_exact_exposure: item.abnormal_wafers_without_observed_exact_exposure ?? [], abnormal_wafers_verified_unexposed: item.abnormal_wafers_verified_unexposed ?? [], normal_wafers_verified_unexposed: item.normal_wafers_verified_unexposed ?? [], abnormal_wafers_not_observed_under_unverified_coverage: item.abnormal_wafers_not_observed_under_unverified_coverage ?? [], normal_wafers_not_observed_under_unverified_coverage: item.normal_wafers_not_observed_under_unverified_coverage ?? [], coverage_evidence_level: item.coverage_evidence_level ?? "UNKNOWN" }} />
            <Details title="Selection, product mix, time, equipment, coverage, and missing evidence" value={{ confounders: item.confounders ?? {}, missing_or_ambiguous_evidence: item.missing_or_ambiguous_evidence ?? {} }} />
            <Details title="Next authorized verification" value={item.next_authorized_verification ?? { status: "NOT_SUPPLIED" }} />
          </article>) : <p>No outcome or counterevidence rows were supplied. No comparative explanation is asserted.</p>}
        </section>

        <section data-panel="evidence" aria-labelledby="p2-evidence-title">
          <h2 id="p2-evidence-title">Sources, permissions, uncertainty, and evidence</h2>
          <h3>Investigation summary</h3>
          {models.summary.claims.length ? models.summary.claims.map((claim, index) => (
            <article key={`${claim.category}-${index}`}>
              <p>{claim.statement}</p>
              <p>{claim.category} · {claim.certainty} · {claim.method}</p>
              <p>Source IDs: {claim.source_ids.join(", ") || "None"}</p>
            </article>
          )) : <p>No positive claim was returned.</p>}
          {models.summary.limitations.length ? <ul>{models.summary.limitations.map((item, index) => <li key={`limitation-${index}`}>{item}</li>)}</ul> : null}
          <p>Evidence hash: <code>{models.evidence.input_sha256}</code></p>
          <p>Permission fields are references returned by the evidence source. This panel does not independently authorize source access.</p>
          {table(makeTable("sources", "Source semantics, data grain, provenance, and permission references", ["Source ID", "Semantic version", "Row grain", "Source hash", "Permission reference", "Evidence inspector"], models.evidence.sources.map(source => [source.id, source.approved_semantic_version, source.grain, source.source_hash, source.permissions_ref ?? "Not supplied"]), models.evidence.sources.map(source => ({ sourceId: source.id }))))}
          <Details title="Investigation scope and source relationships" value={models.evidence.snapshot ? { scope: models.evidence.snapshot.scope ?? {}, source_relationships: models.evidence.snapshot.source_relationships ?? [] } : { status: "NO_SNAPSHOT_ARTIFACT" }} />
          <Details title="Uncertainty and limitations" value={{ uncertainty: models.evidence.uncertainty, limitations: models.evidence.limitations }} />
        </section>
      </> : null}
    </div>
  );
}
