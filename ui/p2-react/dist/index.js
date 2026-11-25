import { jsxs as _jsxs, jsx as _jsx, Fragment as _Fragment } from "react/jsx-runtime";
import { Fragment, useEffect, useState } from "react";
import { buildP2PanelModels } from "./model.js";
export { buildP2PanelModels, summarizeMembershipRefresh } from "./model.js";
const asText = (value, fallback = "Unknown") => typeof value === "string" || typeof value === "number" ? String(value) : fallback;
const asRecords = (value) => Array.isArray(value) ? value.filter((item) => item !== null && typeof item === "object" && !Array.isArray(item)) : [];
const TABLE_PAGE_SIZE = 100;
const JOURNEY_PAGE_SIZE = 25;
const compact = (value) => value.filter(Boolean).join(" / ") || "Unknown";
function lotEvidenceAtEvent(step) {
    const eventLot = asText(step.lot_id_at_event);
    const state = step.membership_state;
    if (state !== "CONFLICTS_WITH_EVENT_ROW_LOT_ID") {
        if (!state)
            return eventLot;
        const label = state === "SOURCE_LINKED_TIME_SCOPED_MEMBERSHIP"
            ? "source-linked membership"
            : state.replaceAll("_", " ").toLowerCase();
        return `${eventLot} · ${label}`;
    }
    const lineage = asRecords([step.lot_lineage])[0];
    const conflicts = asRecords(lineage?.missing_evidence).filter(item => item.reason === "EVENT_LOT_ID_CONFLICTS_WITH_TIME_SCOPED_MEMBERSHIP");
    const candidateLots = [...new Set(conflicts.flatMap(item => Array.isArray(item.candidate_lot_ids) ? item.candidate_lot_ids.filter((value) => typeof value === "string") : []))];
    const membershipRecords = [...new Set(asRecords(lineage?.seeds).flatMap(seed => asRecords(seed.provenance))
            .map(item => item.material_relationship_id).filter((value) => typeof value === "string"))];
    const membership = candidateLots.join(", ") || "unresolved";
    const records = membershipRecords.length ? ` · membership record ${membershipRecords.join(", ")}` : "";
    return `CONFLICT · event row ${eventLot}; time-scoped membership ${membership}${records}`;
}
const evidenceRef = (record) => {
    const sourceId = typeof record.source_id === "string" ? record.source_id : undefined;
    const relationshipId = typeof record.relationship_id === "string" ? record.relationship_id : undefined;
    const recordId = typeof record.record_id === "string" ? record.record_id
        : typeof record.step_instance_id === "string" ? record.step_instance_id
            : typeof record.outcome_id === "string" ? record.outcome_id : undefined;
    return sourceId || relationshipId || recordId
        ? { ...(sourceId ? { sourceId } : {}), ...(relationshipId ? { relationshipId } : {}), ...(recordId ? { recordId } : {}) }
        : undefined;
};
function formatValue(value) {
    if (value === null || value === undefined)
        return "Unknown";
    if (typeof value === "string" || typeof value === "number" || typeof value === "boolean")
        return String(value);
    return JSON.stringify(value, null, 2) ?? "Unknown";
}
function DefaultTable({ caption, columns, rows, onInspectEvidence }) {
    const hasEvidenceColumn = columns.includes("Evidence inspector");
    const [page, setPage] = useState(0);
    useEffect(() => setPage(0), [caption, rows.length]);
    const pageCount = Math.max(1, Math.ceil(rows.length / TABLE_PAGE_SIZE));
    const currentPage = Math.min(page, pageCount - 1);
    const visibleRows = rows.slice(currentPage * TABLE_PAGE_SIZE, (currentPage + 1) * TABLE_PAGE_SIZE);
    const firstVisibleRow = rows.length ? currentPage * TABLE_PAGE_SIZE + 1 : 0;
    const lastVisibleRow = Math.min((currentPage + 1) * TABLE_PAGE_SIZE, rows.length);
    return (_jsxs("div", { className: "p2-paged-table", children: [rows.length > TABLE_PAGE_SIZE ? _jsxs("nav", { className: "p2-page-controls", "aria-label": `Page controls for ${caption}`, children: [_jsxs("span", { "aria-live": "polite", children: ["Rows ", firstVisibleRow, "\u2013", lastVisibleRow, " of ", rows.length] }), _jsx("button", { type: "button", disabled: currentPage === 0, onClick: () => setPage(Math.max(0, currentPage - 1)), children: "Previous rows" }), _jsx("button", { type: "button", disabled: currentPage + 1 >= pageCount, onClick: () => setPage(Math.min(pageCount - 1, currentPage + 1)), children: "Next rows" })] }) : null, _jsx("div", { className: "p2-table-scroll", role: "region", "aria-label": caption, tabIndex: 0, children: _jsxs("table", { children: [_jsx("caption", { children: caption }), _jsx("thead", { children: _jsx("tr", { children: columns.map(column => _jsx("th", { scope: "col", children: column }, column)) }) }), _jsx("tbody", { children: visibleRows.length ? visibleRows.map(row => (_jsxs("tr", { children: [row.cells.map((cell, index) => _jsx("td", { children: cell }, `${row.id}-${index}`)), hasEvidenceColumn ? _jsx("td", { children: row.evidenceRefs?.length ? row.evidenceRefs.map((reference, index) => {
                                            const label = [reference.recordId, reference.sourceId, reference.relationshipId].filter(Boolean).join(" · ");
                                            return onInspectEvidence
                                                ? _jsxs(Fragment, { children: [_jsxs("button", { type: "button", onClick: () => onInspectEvidence(reference), children: ["Inspect ", label || "evidence"] }), index + 1 < (row.evidenceRefs?.length ?? 0) ? " " : ""] }, `${row.id}-ref-${index}`)
                                                : _jsx("span", { children: label || "Evidence reference" }, `${row.id}-ref-${index}`);
                                        }) : "No linked provenance" }) : null] }, row.id))) : _jsx("tr", { children: _jsx("td", { colSpan: columns.length, children: "No records are available." }) }) })] }) })] }));
}
function Details({ title, value }) {
    return _jsxs("details", { children: [_jsx("summary", { children: title }), _jsx("pre", { children: formatValue(value) })] });
}
function DefaultTimeline({ journeys }) {
    return _jsx("div", { "aria-label": "Chronological wafer journey timeline", children: journeys.map(journey => (_jsxs("section", { "aria-label": `Wafer ${journey.wafer_id} chronology`, children: [_jsxs("h3", { children: ["Wafer ", journey.wafer_id, " \u00B7 ", journey.history_status.replaceAll("_", " ")] }), _jsx("ol", { children: journey.steps.map(step => (_jsxs("li", { children: [_jsx("time", { children: asText(step.timestamp) }), " \u2014 ", asText(step.operation), " (", step.step_instance_id, ")", step.time_uncertainty_seconds ? ` · ±${step.time_uncertainty_seconds}s` : "", step.order_uncertain_with?.length ? ` · order uncertain with ${step.order_uncertain_with.join(", ")}` : ""] }, step.step_instance_id))) })] }, journey.wafer_id))) });
}
function makeTable(id, caption, columns, rows, refs = []) {
    return {
        caption,
        columns,
        rows: rows.map((cells, index) => ({
            id: `${id}-${index}`,
            cells,
            ...(refs[index] ? { evidenceRefs: Array.isArray(refs[index]) ? refs[index] : [refs[index]] } : {}),
        })),
    };
}
function routeRows(journeys) {
    return journeys.flatMap(journey => journey.steps.map((step) => [
        journey.wafer_id,
        step.step_instance_id,
        compact([step.route_id, step.route_version]),
        asText(step.operation),
        asText(step.operation_definition_id ?? step.operation_definition_status),
        journey.route_conformance.replaceAll("_", " "),
    ]));
}
function routeRefs(journeys) {
    return journeys.flatMap(journey => journey.steps.map(step => {
        const segment = journey.route_segments?.find(item => Array.isArray(item.step_instance_ids) && item.step_instance_ids.includes(step.step_instance_id));
        const definitionRef = segment?.approved_route_source_id && segment.approved_route_relationship_id
            ? { sourceId: String(segment.approved_route_source_id), relationshipId: String(segment.approved_route_relationship_id) }
            : undefined;
        return [evidenceRef(step), definitionRef].filter((ref) => Boolean(ref));
    }));
}
function journeyEvidenceRefs(journey) {
    const refs = journey.steps.map(step => evidenceRef(step)).filter((ref) => Boolean(ref));
    for (const segment of journey.route_segments ?? []) {
        if (segment.approved_route_source_id && segment.approved_route_relationship_id) {
            refs.push({ sourceId: String(segment.approved_route_source_id), relationshipId: String(segment.approved_route_relationship_id) });
        }
    }
    return refs.filter((ref, index) => refs.findIndex(item => item.sourceId === ref.sourceId && item.relationshipId === ref.relationshipId && item.recordId === ref.recordId) === index);
}
function routeVariantRefs(variants, journeys) {
    return variants.map(variant => journeys
        .filter(journey => variant.wafer_ids.includes(journey.wafer_id))
        .flatMap(journey => journeyEvidenceRefs(journey)));
}
function routeVariantTable(models) {
    const variants = models.journey.route_variants;
    return makeTable("route", "Observed route variants with declared denominator", ["Wafers (count and sample)", "Observed operation sequence", "Order status", "Route versions", "Share of ordered observed histories", "Denominator", "Evidence inspector"], variants.map(variant => [
        `${variant.count} wafer(s)${variant.wafer_ids.length ? ` · sample ${variant.wafer_ids.slice(0, 6).join(", ")}${variant.wafer_ids.length > 6 ? " …" : ""}` : ""}`, variant.operations.join(" → "), variant.order_status,
        compact([...(variant.route_id_sequence ?? []), ...(variant.route_version_sequence ?? [])]),
        typeof variant.share_of_ordered_observed_histories === "number" ? `${(variant.share_of_ordered_observed_histories * 100).toFixed(1)}%` : "Not computed",
        typeof variant.ordered_observed_history_denominator === "number" ? String(variant.ordered_observed_history_denominator) : "Not supplied",
    ]), routeVariantRefs(variants, models.journey.journeys));
}
export function P2ProcessForensicsPanels(props) {
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
    const table = (tableProps) => _jsx(Table, { ...tableProps, ...(onInspectEvidence ? { onInspectEvidence } : {}) });
    const panelProps = className ? { className } : {};
    const statusText = currentEvidence ? `${currentEvidence.status} · ${currentEvidence.mode}` : state.toUpperCase();
    const journeyTable = makeTable("journey", "Chronological process step instances", ["Wafer", "Step instance", "Operation", "Event time / uncertainty", "Recorded time", "Lot evidence at event", "Tool / chamber", "Operation definition", "History / route state", "Evidence inspector"], matchingJourneys.flatMap(journey => journey.steps.map(step => [
        journey.wafer_id, step.step_instance_id, asText(step.operation),
        `${asText(step.timestamp)}${step.time_uncertainty_seconds ? ` · ±${step.time_uncertainty_seconds}s` : ""}${step.order_uncertain_with?.length ? ` · unordered with ${step.order_uncertain_with.join(", ")}` : ""}`,
        asText(step.recorded_at), lotEvidenceAtEvent(step), compact([step.tool_id, step.chamber_id]),
        asText(step.operation_definition_id ?? step.operation_definition_status),
        `${journey.history_status} / ${journey.route_conformance}`,
    ])), matchingJourneys.flatMap(journey => journey.steps.map(step => evidenceRef(step))));
    return (_jsxs("div", { ...panelProps, "data-p2-module": "1.0.0", "aria-label": "FAB Process Forensics", children: [_jsxs("header", { children: [_jsx("h2", { children: "FAB Process Forensics" }), _jsxs("p", { role: state === "error" || currentEvidence?.status === "REFUSED" || currentEvidence?.status === "ERROR" ? "alert" : "status", "aria-live": "polite", children: [statusText, currentEvidence ? ` · Investigation ${currentEvidence.investigation_id}` : ""] }), currentEvidence?.mode === "SYNTHETIC_DEMO" ? _jsx("p", { role: "note", children: "Synthetic demonstration evidence. It does not establish company source approval." }) : null, state === "loading" && props.onCancel ? _jsx("button", { type: "button", onClick: props.onCancel, children: "Cancel investigation" }) : null, (state === "error" || state === "cancelled") && props.onRetry ? _jsx("button", { type: "button", onClick: props.onRetry, children: "Retry investigation" }) : null, props.onStartInvestigation ? _jsx("button", { type: "button", onClick: props.onStartInvestigation, children: "Start or change investigation" }) : null, currentEvidence && props.onExportEvidence ? _jsx("button", { type: "button", onClick: () => props.onExportEvidence?.(currentEvidence), children: "Export reproducible evidence" }) : null, state === "error" ? _jsx("p", { role: "alert", children: props.errorMessage || "The host could not complete this investigation." }) : null, state === "cancelled" ? _jsx("p", { role: "status", children: "Investigation cancelled. No partial evidence is displayed." }) : null, currentEvidence?.status === "ERROR" ? _jsx("p", { role: "alert", children: "The evidence envelope reports an analysis error. No findings are displayed." }) : null, !evidence && state === "idle" ? _jsx("p", { children: "Select an abnormal wafer or lot, or a suspected equipment interval, in the host to begin." }) : null, !evidence && state === "ready" ? _jsx("p", { role: "status", children: "The host returned no evidence envelope." }) : null, currentEvidence?.status === "REFUSED" ? _jsx("p", { role: "alert", children: "This investigation was refused. Review the stated limitations and source permissions with the host before retrying." }) : null] }), models ? suppressFindings ? _jsxs("section", { "data-panel": "evidence", "aria-labelledby": "p2-unavailable-title", children: [_jsx("h2", { id: "p2-unavailable-title", children: "Analysis findings withheld" }), _jsx("p", { children: models.summary.status === "REFUSED" ? "The analysis was refused. No route, exposure, or hypothesis findings are displayed." : "The analysis returned an error. No route, exposure, or hypothesis findings are displayed." }), models.summary.limitations.length ? _jsx("ul", { children: models.summary.limitations.map((item, index) => _jsx("li", { children: item }, `refusal-limitation-${index}`)) }) : _jsx("p", { children: "No additional reason was supplied." }), _jsxs("p", { children: ["Evidence hash: ", _jsx("code", { children: models.evidence.input_sha256 })] })] }) : _jsxs(_Fragment, { children: [_jsxs("section", { "data-panel": "journey", "aria-labelledby": "p2-journey-title", children: [_jsx("h2", { id: "p2-journey-title", children: "Wafer and lot journey" }), models.journey.journeys.length ? _jsxs(_Fragment, { children: [_jsx("label", { htmlFor: "p2-journey-filter", children: "Find a wafer, lot, step instance, or operation" }), _jsx("input", { id: "p2-journey-filter", type: "search", value: journeyFilter, onChange: event => { setJourneyFilter(event.currentTarget.value); setJourneyPage(0); }, "aria-label": "Find a wafer, lot, step instance, or operation" }), journeyCount > JOURNEY_PAGE_SIZE ? _jsxs("nav", { className: "p2-page-controls", "aria-label": "Journey page controls", children: [_jsxs("span", { "aria-live": "polite", children: ["Showing journeys ", journeyStart + 1, "\u2013", Math.min(journeyStart + JOURNEY_PAGE_SIZE, journeyCount), " of ", journeyCount] }), _jsx("button", { type: "button", disabled: currentJourneyPage === 0, onClick: () => setJourneyPage(Math.max(0, currentJourneyPage - 1)), children: "Previous journeys" }), _jsx("button", { type: "button", disabled: currentJourneyPage + 1 >= journeyPageCount, onClick: () => setJourneyPage(Math.min(journeyPageCount - 1, currentJourneyPage + 1)), children: "Next journeys" })] }) : _jsxs("p", { role: "status", children: ["Showing ", journeyCount, " matching wafer journey", journeyCount === 1 ? "" : "s", "."] }), journeyCount ? (components?.JourneyTimeline
                                        ? _jsx(components.JourneyTimeline, { journeys: visibleJourneys, ...(onInspectEvidence ? { onInspectEvidence } : {}) })
                                        : _jsx(DefaultTimeline, { journeys: visibleJourneys }))
                                        : _jsx("p", { role: "status", children: "No wafer or lot journey matches this search." }), journeyCount ? table(journeyTable) : null, visibleJourneys.map(journey => _jsxs("details", { children: [_jsxs("summary", { children: ["Inspect ", journey.wafer_id, " lineage, membership, route segments, and rework"] }), _jsxs("p", { children: ["History: ", journey.history_status, ". Route conformance: ", journey.route_conformance, "."] }), _jsx(Details, { title: "History coverage", value: journey.history_coverage ?? { status: "COVERAGE_UNKNOWN" } }), _jsx(Details, { title: "Time-scoped lot membership and lineage paths", value: journey.lot_lineage_paths ?? [] }), _jsx(Details, { title: "Material relationships and provenance", value: journey.material_relationships ?? [] }), _jsx(Details, { title: "Route segments and explicit rework edges", value: { route_segments: journey.route_segments ?? [], rework_edges: journey.rework_edges ?? [] } })] }, `${journey.wafer_id}-lineage`))] }) : _jsx("p", { children: "No journey was produced. Missing event history is not interpreted as an empty manufacturing path." })] }), _jsxs("section", { "data-panel": "exposure", "aria-labelledby": "p2-exposure-title", children: [_jsx("h2", { id: "p2-exposure-title", children: "Exposure evidence and comparator populations" }), models.exposure.populations.length
                                ? table(makeTable("population", "Exposure classification and evidence basis", ["Classification", "Wafer count", "Wafer IDs", "Basis"], models.exposure.populations.map(population => [population.classification, String(population.count), population.wafer_ids.join(", ") || "None", population.basis])))
                                : _jsx("p", { children: "No source-backed exposure populations were supplied." }), models.exposure.analysis ? _jsxs(_Fragment, { children: [_jsxs("p", { children: [asText(models.exposure.analysis.scope_type), " ", asText(models.exposure.analysis.scope_id), " \u00B7 ", formatValue(models.exposure.analysis.window)] }), _jsxs("p", { children: ["Coverage evidence level: ", _jsx("strong", { children: asText(models.exposure.analysis.coverage_evidence_level, "UNKNOWN") }), ". Only SOURCE_VERIFIED coverage supports an observed-unexposed comparator. ", asText(models.exposure.analysis.coverage_reason, "Coverage status not supplied.")] }), _jsx("p", { children: "Condition-event timing is contextual evidence. Time overlap alone does not establish processing exposure or cause." }), table(makeTable("exposure", "Source-linked processing event exposure evidence", ["Wafer", "Step instance", "Classification", "Event time", "Exact scope", "Source relationship", "Evidence inspector"], asRecords(models.exposure.analysis.evidence).map(row => [
                                        asText(row.wafer_id), asText(row.step_instance_id), asText(row.classification), asText(row.timestamp_utc ?? row.timestamp), compact([asText(row.scope_type, ""), asText(row.scope_id, "")]), compact([asText(row.source_id, ""), asText(row.relationship_id, "")]),
                                    ]), asRecords(models.exposure.analysis.evidence).map(row => evidenceRef(row)))), _jsx(Details, { title: "Coverage scope, authority claim, maintenance context, and uncertainty", value: { coverage: models.exposure.analysis.coverage_evidence ?? {}, asserted_nonmatches: models.exposure.analysis.not_observed_exposed_under_unverified_coverage ?? [], condition_event_status: models.exposure.analysis.condition_event_status, condition_events: models.exposure.analysis.condition_event_evidence ?? [], uncertainty: evidence?.uncertainty ?? {} } })] }) : null] }), _jsxs("section", { "data-panel": "route", "aria-labelledby": "p2-route-title", children: [_jsx("h2", { id: "p2-route-title", children: "Route variants and conformance" }), models.journey.route_variants.length
                                ? table(routeVariantTable(models))
                                : _jsx("p", { children: "No ordered observed route variants are available." }), models.journey.route_variants.length ? _jsx(Details, { title: "Complete route-variant wafer membership sets", value: models.journey.route_variants.map(variant => ({
                                    operations: variant.operations,
                                    route_ids: variant.route_id_sequence ?? [],
                                    route_versions: variant.route_version_sequence ?? [],
                                    order_status: variant.order_status,
                                    wafer_ids: variant.wafer_ids,
                                    denominator: variant.ordered_observed_history_denominator ?? null,
                                })) }) : null, models.journey.route_population_summary ? _jsx(Details, { title: "Route coverage and population denominator", value: models.journey.route_population_summary }) : null, _jsx("p", { children: "Route conformance is asserted only against a verified, effective route definition and adequate history coverage. Incomplete histories remain unknown." }), table(makeTable("route-conformance", "Actual step instances and route state", ["Wafer", "Step instance", "Route / version", "Actual operation", "Definition", "Conformance", "Evidence inspector"], routeRows(models.journey.journeys), routeRefs(models.journey.journeys)))] }), _jsxs("section", { "data-panel": "counterevidence", "aria-labelledby": "p2-counter-title", children: [_jsx("h2", { id: "p2-counter-title", children: "Competing hypotheses and counterevidence" }), models.counterevidence.investigations.length ? models.counterevidence.investigations.map((item, index) => _jsxs("article", { children: [_jsx("h3", { children: asText(item.question, "Investigation hypothesis") }), _jsx("p", { children: asText(item.interpretation, "Interpretation unavailable.") }), _jsxs("p", { children: ["Statistical association: ", formatValue(item.statistical_association), ". Proposed explanation: ", formatValue(item.proposed_explanation), ". Causal conclusion: ", formatValue(item.causal_conclusion), "."] }), _jsx(Details, { title: "Supporting and contradicting observations", value: { supporting: item.supporting_observations ?? [], contradicting: item.contradicting_observations ?? {} } }), _jsx(Details, { title: "Shared exposure, verified nonmatches, and asserted nonmatches", value: { normal_wafers_with_exact_exposure: item.normal_wafers_with_exact_exposure ?? [], abnormal_wafers_without_observed_exact_exposure: item.abnormal_wafers_without_observed_exact_exposure ?? [], abnormal_wafers_verified_unexposed: item.abnormal_wafers_verified_unexposed ?? [], normal_wafers_verified_unexposed: item.normal_wafers_verified_unexposed ?? [], abnormal_wafers_not_observed_under_unverified_coverage: item.abnormal_wafers_not_observed_under_unverified_coverage ?? [], normal_wafers_not_observed_under_unverified_coverage: item.normal_wafers_not_observed_under_unverified_coverage ?? [], coverage_evidence_level: item.coverage_evidence_level ?? "UNKNOWN" } }), _jsx(Details, { title: "Selection, product mix, time, equipment, coverage, and missing evidence", value: { confounders: item.confounders ?? {}, missing_or_ambiguous_evidence: item.missing_or_ambiguous_evidence ?? {} } }), _jsx(Details, { title: "Next authorized verification", value: item.next_authorized_verification ?? { status: "NOT_SUPPLIED" } })] }, `hypothesis-${index}`)) : _jsx("p", { children: "No outcome or counterevidence rows were supplied. No comparative explanation is asserted." })] }), _jsxs("section", { "data-panel": "evidence", "aria-labelledby": "p2-evidence-title", children: [_jsx("h2", { id: "p2-evidence-title", children: "Sources, permissions, uncertainty, and evidence" }), _jsx("h3", { children: "Investigation summary" }), models.summary.claims.length ? models.summary.claims.map((claim, index) => (_jsxs("article", { children: [_jsx("p", { children: claim.statement }), _jsxs("p", { children: [claim.category, " \u00B7 ", claim.certainty, " \u00B7 ", claim.method] }), _jsxs("p", { children: ["Source IDs: ", claim.source_ids.join(", ") || "None"] })] }, `${claim.category}-${index}`))) : _jsx("p", { children: "No positive claim was returned." }), models.summary.limitations.length ? _jsx("ul", { children: models.summary.limitations.map((item, index) => _jsx("li", { children: item }, `limitation-${index}`)) }) : null, _jsxs("p", { children: ["Evidence hash: ", _jsx("code", { children: models.evidence.input_sha256 })] }), _jsx("p", { children: "Permission fields are references returned by the evidence source. This panel does not independently authorize source access." }), table(makeTable("sources", "Source semantics, data grain, provenance, and permission references", ["Source ID", "Semantic version", "Row grain", "Source hash", "Permission reference", "Evidence inspector"], models.evidence.sources.map(source => [source.id, source.approved_semantic_version, source.grain, source.source_hash, source.permissions_ref ?? "Not supplied"]), models.evidence.sources.map(source => ({ sourceId: source.id })))), _jsx(Details, { title: "Investigation scope and source relationships", value: models.evidence.snapshot ? { scope: models.evidence.snapshot.scope ?? {}, source_relationships: models.evidence.snapshot.source_relationships ?? [] } : { status: "NO_SNAPSHOT_ARTIFACT" } }), _jsx(Details, { title: "Uncertainty and limitations", value: { uncertainty: models.evidence.uncertainty, limitations: models.evidence.limitations } })] })] }) : null] }));
}
