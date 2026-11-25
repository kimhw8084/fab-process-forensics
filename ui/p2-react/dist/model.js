function isRecord(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
}
function records(value) {
    return Array.isArray(value) ? value.filter(isRecord) : [];
}
function strings(value) {
    return Array.isArray(value) ? value.filter((item) => typeof item === "string") : [];
}
function getJourneyTransformation(value) {
    return records(value).find(item => item.id === "p2-journey-and-route-variants-v1") ?? null;
}
function getSnapshot(value) {
    return records(value).find(item => item.kind === "investigation_snapshot") ?? null;
}
function readJourneys(value) {
    if (!value)
        return [];
    return records(value.journeys).filter(item => typeof item.wafer_id === "string" && typeof item.history_status === "string"
        && typeof item.route_conformance === "string" && Array.isArray(item.steps)
        && item.steps.every(step => isRecord(step) && typeof step.step_instance_id === "string"));
}
function readRoutes(value) {
    if (!value)
        return [];
    return records(value.route_variants).filter(item => typeof item.count === "number" && Array.isArray(item.operations)
        && item.operations.every(operation => typeof operation === "string")
        && Array.isArray(item.wafer_ids) && item.wafer_ids.every(wafer => typeof wafer === "string")
        && typeof item.order_status === "string");
}
function readSources(value) {
    return records(value).flatMap(item => {
        if (typeof item.id !== "string" || typeof item.approved_semantic_version !== "string"
            || typeof item.grain !== "string" || typeof item.source_hash !== "string")
            return [];
        return [{
                id: item.id,
                approved_semantic_version: item.approved_semantic_version,
                grain: item.grain,
                source_hash: item.source_hash,
                ...(typeof item.permissions_ref === "string" ? { permissions_ref: item.permissions_ref } : {}),
                ...(typeof item.observed_at === "string" ? { observed_at: item.observed_at } : {}),
            }];
    });
}
function readPopulations(value) {
    return records(value).filter(item => typeof item.classification === "string" && typeof item.count === "number"
        && Array.isArray(item.wafer_ids) && typeof item.basis === "string");
}
function requireEvidenceEnvelope(value) {
    if (!isRecord(value) || value.schema_version !== "1.0.0" || value.product_id !== "p2"
        || typeof value.investigation_id !== "string"
        || !["VALID", "PARTIAL", "INCONCLUSIVE", "REFUSED", "ERROR"].includes(String(value.status))
        || !["SYNTHETIC_DEMO", "INTERNAL_AUTHORIZED"].includes(String(value.mode))
        || !Array.isArray(value.claims) || !value.claims.every(claim => isRecord(claim)
        && typeof claim.statement === "string" && typeof claim.category === "string"
        && Array.isArray(claim.source_ids) && typeof claim.method === "string" && typeof claim.certainty === "string")
        || !Array.isArray(value.sources) || !value.sources.every(source => isRecord(source)
        && typeof source.id === "string" && typeof source.approved_semantic_version === "string"
        && typeof source.grain === "string" && typeof source.source_hash === "string")
        || !Array.isArray(value.assumptions) || !Array.isArray(value.limitations)
        || !isRecord(value.provenance) || typeof value.provenance.input_sha256 !== "string") {
        throw new TypeError("A contract-v1 P2 evidence envelope is required.");
    }
}
/** Build typed, read-only panel models without adding joins or changing evidence. */
export function buildP2PanelModels(value) {
    requireEvidenceEnvelope(value);
    const journey = getJourneyTransformation(value.transformations);
    const snapshot = getSnapshot(value.artifacts);
    const snapshotJourney = isRecord(snapshot?.journey) ? snapshot.journey : null;
    const sourceJourney = journey ?? snapshotJourney;
    const exposureTransform = records(value.transformations).find(item => item.id === "p2-exposure-evidence-v1");
    const analysis = isRecord(snapshot?.exposure_analysis)
        ? snapshot.exposure_analysis
        : (isRecord(exposureTransform?.exposure) ? exposureTransform.exposure : null);
    const uncertainty = isRecord(value.uncertainty) ? value.uncertainty : {};
    return {
        summary: {
            status: value.status,
            mode: value.mode,
            investigation_id: value.investigation_id,
            claims: value.claims,
            limitations: value.limitations,
        },
        journey: {
            transformation: journey,
            journeys: readJourneys(sourceJourney),
            route_variants: readRoutes(sourceJourney),
            route_population_summary: sourceJourney && isRecord(sourceJourney.route_population_summary)
                ? sourceJourney.route_population_summary : null,
        },
        exposure: {
            populations: readPopulations(value.populations),
            analysis,
        },
        counterevidence: { investigations: records(value.counterevidence) },
        evidence: {
            sources: readSources(value.sources),
            snapshot,
            uncertainty,
            limitations: strings(value.limitations),
            input_sha256: value.provenance.input_sha256,
        },
    };
}
/** Summarize refreshed membership evidence without treating missing rows as resolution. */
export function summarizeMembershipRefresh(value, targetWaferIds) {
    requireEvidenceEnvelope(value);
    const journeys = buildP2PanelModels(value).journey.journeys;
    return [...new Set(targetWaferIds)].map(waferId => {
        const journey = journeys.find(item => item.wafer_id === waferId);
        if (!journey) {
            return `Wafer ${waferId}: no refreshed journey was returned; the previous membership question remains unresolved.`;
        }
        const flags = strings(journey.history_flags);
        const ambiguous = flags.includes("MATERIAL_MEMBERSHIP_AMBIGUOUS")
            || journey.steps.some(step => step.membership_state === "CONFLICTS_WITH_EVENT_ROW_LOT_ID");
        const relationships = records(journey.material_relationships);
        const recordIds = [...new Set(relationships.map(item => item.record_id)
                .filter((item) => typeof item === "string"))];
        const sourceIds = [...new Set(relationships.map(item => item.source_id)
                .filter((item) => typeof item === "string"))];
        const relationshipIds = [...new Set(relationships.map(item => item.relationship_id)
                .filter((item) => typeof item === "string"))];
        const coverage = isRecord(journey.history_coverage)
            ? journey.history_coverage.coverage_evidence_level : "UNKNOWN";
        const evidence = relationships.length
            ? `${relationships.length} refreshed relationship record(s)${recordIds.length ? ` (${recordIds.join(", ")})` : ""}${sourceIds.length ? ` from ${sourceIds.join(", ")}` : ""}${relationshipIds.length ? ` via ${relationshipIds.join(", ")}` : ""}`
            : "no material relationship records";
        if (ambiguous) {
            return `Wafer ${waferId}: membership remains ambiguous (${journey.history_status}; coverage ${String(coverage)}); ${evidence}. Inspect the linked source records.`;
        }
        return `Wafer ${waferId}: refreshed history is ${journey.history_status} (coverage ${String(coverage)}); ${evidence}. No explicit ambiguity flag was returned, which does not establish that the prior membership question is resolved.`;
    });
}
