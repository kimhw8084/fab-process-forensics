import type { ComponentType } from "react";
export type EvidenceStatus = "VALID" | "PARTIAL" | "INCONCLUSIVE" | "REFUSED" | "ERROR";
export type InvestigationMode = "SYNTHETIC_DEMO" | "INTERNAL_AUTHORIZED";
export type P2CoverageEvidenceLevel = "SOURCE_VERIFIED" | "ASSERTED_UNVERIFIED" | "PARTIAL" | "UNKNOWN" | "CONTRADICTORY";
export type JsonRecord = Readonly<Record<string, unknown>>;
export interface P2CoverageEvidence extends JsonRecord {
    readonly coverage_evidence_level: P2CoverageEvidenceLevel;
    readonly population_kind?: string;
    readonly covered_wafer_ids?: readonly string[];
    readonly covered_lot_ids?: readonly string[];
    readonly covered_operation_ids?: readonly string[];
    readonly window_start?: string;
    readonly window_end?: string;
    readonly valid_until?: string;
    readonly source_ids?: readonly string[];
    readonly covered_source_ids?: readonly string[];
    readonly source_authority_claim?: string | null;
    readonly relationship_id?: string | null;
    readonly record_id?: string | null;
    readonly missing_record_ids?: readonly string[];
    readonly accepted_for_query?: boolean;
}
export interface P2Claim {
    readonly statement: string;
    readonly category: "DESCRIPTIVE" | "ASSOCIATION" | "PREDICTION" | "CAUSAL_ESTIMATE" | "INTERVENTION_VALIDATED";
    readonly source_ids: readonly string[];
    readonly method: string;
    readonly certainty: "SUPPORTED" | "CONDITIONAL" | "INCONCLUSIVE";
}
export interface P2SourceReference {
    readonly id: string;
    readonly approved_semantic_version: string;
    readonly grain: string;
    readonly source_hash: string;
    readonly permissions_ref?: string;
    readonly observed_at?: string;
}
export interface P2EvidenceReference {
    readonly sourceId?: string;
    readonly relationshipId?: string;
    readonly recordId?: string;
}
export interface P2ProcessStep extends JsonRecord {
    readonly step_instance_id: string;
    readonly operation?: string;
    readonly operation_definition_id?: string;
    readonly operation_definition_status?: string;
    readonly timestamp?: string;
    readonly recorded_at?: string;
    readonly time_uncertainty_seconds?: number;
    readonly order_uncertain_with?: readonly string[];
    readonly route_id?: string;
    readonly route_version?: string;
    readonly lot_id_at_event?: string;
    readonly tool_id?: string;
    readonly chamber_id?: string;
    readonly source_id?: string;
    readonly relationship_id?: string;
    readonly membership_state?: string;
    readonly lot_lineage?: JsonRecord;
}
export interface P2Journey extends JsonRecord {
    readonly wafer_id: string;
    readonly history_status: string;
    readonly route_conformance: string;
    readonly history_coverage?: P2CoverageEvidence | JsonRecord;
    readonly steps: readonly P2ProcessStep[];
    readonly route_segments?: readonly JsonRecord[];
    readonly rework_edges?: readonly JsonRecord[];
    readonly material_relationships?: readonly JsonRecord[];
    readonly lot_lineage_paths?: readonly JsonRecord[];
}
export interface P2RouteVariant extends JsonRecord {
    readonly count: number;
    readonly operations: readonly string[];
    readonly wafer_ids: readonly string[];
    readonly order_status: string;
    readonly route_id_sequence?: readonly (string | null)[];
    readonly route_version_sequence?: readonly (string | null)[];
    readonly share_of_ordered_observed_histories?: number;
    readonly ordered_observed_history_denominator?: number;
}
export interface P2Population extends JsonRecord {
    readonly classification: string;
    readonly count: number;
    readonly wafer_ids: readonly string[];
    readonly basis: string;
}
export interface P2EvidenceEnvelope {
    readonly schema_version: "1.0.0";
    readonly investigation_id: string;
    readonly product_id: "p2";
    readonly mode: InvestigationMode;
    readonly status: EvidenceStatus;
    readonly claims: readonly P2Claim[];
    readonly sources: readonly P2SourceReference[];
    readonly assumptions: readonly string[];
    readonly limitations: readonly string[];
    readonly provenance: Readonly<{
        readonly engine_version: string;
        readonly input_sha256: string;
        readonly [key: string]: unknown;
    }>;
    readonly transformations?: readonly JsonRecord[];
    readonly populations?: readonly P2Population[];
    readonly counterevidence?: readonly JsonRecord[];
    readonly uncertainty?: JsonRecord;
    readonly artifacts?: readonly JsonRecord[];
    readonly units?: JsonRecord;
}
export interface P2PanelModels {
    readonly summary: Readonly<{
        readonly status: EvidenceStatus;
        readonly mode: InvestigationMode;
        readonly investigation_id: string;
        readonly claims: readonly P2Claim[];
        readonly limitations: readonly string[];
    }>;
    readonly journey: Readonly<{
        readonly transformation: JsonRecord | null;
        readonly journeys: readonly P2Journey[];
        readonly route_variants: readonly P2RouteVariant[];
        readonly route_population_summary: JsonRecord | null;
    }>;
    readonly exposure: Readonly<{
        readonly populations: readonly P2Population[];
        readonly analysis: JsonRecord | null;
    }>;
    readonly counterevidence: Readonly<{
        readonly investigations: readonly JsonRecord[];
    }>;
    readonly evidence: Readonly<{
        readonly sources: readonly P2SourceReference[];
        readonly snapshot: JsonRecord | null;
        readonly uncertainty: JsonRecord;
        readonly limitations: readonly string[];
        readonly input_sha256: string;
    }>;
}
export interface P2TableRow {
    readonly id: string;
    readonly cells: readonly string[];
    readonly evidenceRefs?: readonly P2EvidenceReference[];
}
export interface P2TableProps {
    readonly caption: string;
    readonly columns: readonly string[];
    readonly rows: readonly P2TableRow[];
    readonly onInspectEvidence?: (reference: P2EvidenceReference) => void;
}
export interface P2JourneyTimelineProps {
    readonly journeys: readonly P2Journey[];
    readonly onInspectEvidence?: (reference: P2EvidenceReference) => void;
}
/** P1 adapts its existing accessible table and journey visualization here. */
export interface P2HostComponents {
    readonly Table?: ComponentType<P2TableProps>;
    readonly JourneyTimeline?: ComponentType<P2JourneyTimelineProps>;
}
export type P2RequestState = "idle" | "loading" | "ready" | "error" | "cancelled";
export interface P2ProcessForensicsProps {
    readonly state: P2RequestState;
    readonly evidence?: P2EvidenceEnvelope;
    readonly errorMessage?: string;
    readonly components?: P2HostComponents;
    readonly onCancel?: () => void;
    readonly onRetry?: () => void;
    readonly onStartInvestigation?: () => void;
    readonly onExportEvidence?: (evidence: P2EvidenceEnvelope) => void;
    readonly onInspectEvidence?: (reference: P2EvidenceReference) => void;
    readonly className?: string;
}
