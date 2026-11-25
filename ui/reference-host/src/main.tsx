import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { createRoot } from "react-dom/client";
import { P2ProcessForensicsPanels, summarizeMembershipRefresh } from "../../p2-react/src/index.js";
import type { P2EvidenceEnvelope, P2EvidenceReference, P2RequestState } from "../../p2-react/src/types.js";
import "../../styles.css";
import "./reference-host.css";

interface ReferenceOptions {
  readonly mode: string;
  readonly protocol_version: string;
  readonly default_suspected_exposure: Readonly<{
    chamber_id?: string;
    tool_id?: string;
    start: string;
    end: string;
  }>;
  readonly cohort_wafer_ids: readonly string[];
  readonly abnormal_wafer_ids: readonly string[];
  readonly chamber_ids: readonly string[];
  readonly tool_ids: readonly string[];
  readonly sources: readonly { readonly id: string; readonly source_hash: string }[];
  readonly audited_reads: readonly Record<string, unknown>[];
  readonly onboarding?: Readonly<{
    readonly mode: "SYNTHETIC_FIXTURE_ONLY";
    readonly proposal_sha256: string;
    readonly decision: string;
    readonly reviewer_id: string;
    readonly server_authorization_established: false;
    readonly company_qualified: false;
    readonly source_role_mappings: readonly Readonly<{
      readonly dataset_role: string;
      readonly source_id: string;
      readonly relationship_id: string;
      readonly time_field: string;
      readonly field_mapping: Readonly<Record<string, string | null>>;
      readonly relationship_type?: string | null;
    }>[];
  }>;
  readonly company_source_authorized: false;
  readonly mock_peer_permission_enforced: true;
}

interface InvestigationRequest {
  readonly target_wafer_ids: readonly string[];
  readonly cohort_wafer_ids: readonly string[];
  readonly time_window: Readonly<{ start: string; end: string }>;
  readonly suspected_exposure: Readonly<{
    chamber_id?: string;
    tool_id?: string;
    start: string;
    end: string;
  }>;
  readonly mock_peer_delay_ms?: number;
}

interface InspectorSelection {
  readonly reference: P2EvidenceReference;
  readonly details: readonly unknown[];
}

type FollowUpCandidate = Readonly<Record<string, unknown>>;

function membershipConflictProposal(evidence: P2EvidenceEnvelope | undefined): FollowUpCandidate | null {
  for (const investigation of evidence?.counterevidence ?? []) {
    const verification = investigation.next_authorized_verification as Record<string, unknown> | undefined;
    const candidates = verification?.candidates;
    if (!Array.isArray(candidates)) continue;
    const candidate = candidates.find(item => item && typeof item === "object"
      && (item as Record<string, unknown>).category === "LOT_MEMBERSHIP_CONFLICT");
    if (candidate && typeof candidate === "object") return candidate as FollowUpCandidate;
  }
  return null;
}

const root = document.querySelector<HTMLDivElement>("#root");
if (!root) throw new Error("The reference host root element is missing.");

const localToken = document.querySelector<HTMLMetaElement>('meta[name="fabintel-local-token"]')?.content ?? "";

async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      "X-Fabintel-Token": localToken,
      ...(init.headers ?? {}),
    },
  });
  const body = await response.json() as T & { readonly error?: string; readonly status?: string; readonly reason?: string };
  if (!response.ok) {
    const error = new Error(body.error ?? body.reason ?? `Local service returned HTTP ${response.status}.`);
    Object.assign(error, { status: response.status, response: body });
    throw error;
  }
  return body;
}

function uniqueId(): string {
  return crypto.randomUUID();
}

function utcTimestamp(value: string): string {
  if (!value) throw new Error("Choose both ends of the investigation time range.");
  const parsed = new Date(value);
  if (Number.isNaN(parsed.valueOf())) throw new Error("The selected time range is invalid.");
  return parsed.toISOString();
}

function localInputForUtc(value: string): string {
  const date = new Date(value);
  const pad = (number: number) => String(number).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function selectedValues(select: HTMLSelectElement): string[] {
  return Array.from(select.selectedOptions, option => option.value);
}

function evidenceDetails(evidence: P2EvidenceEnvelope | undefined, reference: P2EvidenceReference): unknown[] {
  if (!evidence) return [];
  const artifact = evidence.artifacts?.find(item => item.kind === "investigation_snapshot");
  const relationships = Array.isArray(artifact?.source_relationships) ? artifact.source_relationships : [];
  const journey = artifact?.journey as { readonly journeys?: readonly Record<string, unknown>[]; readonly material_relationships?: readonly Record<string, unknown>[] } | undefined;
  const rows: unknown[] = [];
  if (reference.sourceId) rows.push(...evidence.sources.filter(source => source.id === reference.sourceId));
  if (reference.relationshipId) rows.push(...relationships.filter(item => item.id === reference.relationshipId));
  if (reference.recordId) {
    rows.push(...(journey?.material_relationships ?? []).filter(item => item.record_id === reference.recordId));
    for (const wafer of journey?.journeys ?? []) {
      rows.push(...((wafer.material_relationships as readonly Record<string, unknown>[] | undefined) ?? []).filter(item => item.record_id === reference.recordId));
      rows.push(...((wafer.steps as readonly Record<string, unknown>[] | undefined) ?? []).filter(item => item.step_instance_id === reference.recordId));
    }
  }
  return rows;
}

function downloadEvidence(evidence: P2EvidenceEnvelope): void {
  const body = `${JSON.stringify(evidence, null, 2)}\n`;
  const blob = new Blob([body], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `p2-investigation-${evidence.investigation_id}.json`;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function ReferenceHost() {
  const [options, setOptions] = useState<ReferenceOptions | null>(null);
  const [optionError, setOptionError] = useState<string | null>(null);
  const [state, setState] = useState<P2RequestState>("idle");
  const [evidence, setEvidence] = useState<P2EvidenceEnvelope | undefined>();
  const [errorMessage, setErrorMessage] = useState("");
  const [selectedTargets, setSelectedTargets] = useState<string[]>([]);
  const [selectedCohort, setSelectedCohort] = useState<string[]>([]);
  const [scopeType, setScopeType] = useState<"chamber_id" | "tool_id">("chamber_id");
  const [scopeId, setScopeId] = useState("");
  const [start, setStart] = useState(() => localInputForUtc("2026-11-21T03:00:00Z"));
  const [end, setEnd] = useState(() => localInputForUtc("2026-11-21T06:00:00Z"));
  const [mockPeerDelay, setMockPeerDelay] = useState(0);
  const [followUpState, setFollowUpState] = useState<"idle" | "loading" | "denied" | "complete" | "error">("idle");
  const [followUpStatus, setFollowUpStatus] = useState("");
  const [selection, setSelection] = useState<InspectorSelection | null>(null);
  const [requestStatus, setRequestStatus] = useState("Loading source-backed synthetic options from the configured MCP peer.");
  const activeRequestId = useRef<string | null>(null);
  const lastRequest = useRef<InvestigationRequest | null>(null);
  const formRef = useRef<HTMLElement>(null);

  useEffect(() => {
    let mounted = true;
    api<ReferenceOptions>("/api/reference/options")
      .then(result => {
        if (!mounted) return;
        setOptions(result);
        setSelectedTargets(result.abnormal_wafer_ids.slice(0, 10));
        setSelectedCohort([...result.cohort_wafer_ids]);
        const initialScopeType = result.default_suspected_exposure.chamber_id ? "chamber_id" : "tool_id";
        const initialScope = result.default_suspected_exposure.chamber_id ?? result.default_suspected_exposure.tool_id ?? "";
        setScopeType(initialScopeType);
        setScopeId(initialScope);
        setStart(localInputForUtc(result.default_suspected_exposure.start));
        setEnd(localInputForUtc(result.default_suspected_exposure.end));
        setRequestStatus(`Loaded ${result.abnormal_wafer_ids.length} abnormal target option(s) and ${result.cohort_wafer_ids.length} observed cohort member(s) through read-only MCP calls.`);
      })
      .catch(error => {
        if (!mounted) return;
        setOptionError(error instanceof Error ? error.message : String(error));
        setRequestStatus("Source options could not be loaded. Retry the configured local MCP request.");
      });
    return () => { mounted = false; };
  }, []);

  const scopeOptions = useMemo(() => {
    if (!options) return [];
    return scopeType === "chamber_id" ? options.chamber_ids : options.tool_ids;
  }, [options, scopeType]);

  const submit = useCallback(async (request: InvestigationRequest) => {
    const requestId = uniqueId();
    activeRequestId.current = requestId;
    lastRequest.current = request;
    setState("loading");
    setEvidence(undefined);
    setSelection(null);
    setErrorMessage("");
    setRequestStatus("Discovering the configured synthetic MCP peer, validating approved-fixture semantics, then reading seven bounded source roles.");
    setFollowUpState("idle");
    setFollowUpStatus("");
    try {
      const result = await api<P2EvidenceEnvelope>("/api/reference/investigate", {
        method: "POST",
        headers: { "X-Fabintel-Request-ID": requestId },
        body: JSON.stringify(request),
      });
      setEvidence(result);
      setState("ready");
      setRequestStatus("Investigation completed. Review chronology, exposure coverage, route status, competing evidence, and source provenance.");
    } catch (error) {
      const response = error && typeof error === "object" ? (error as { response?: { status?: string; reason?: string } }).response : undefined;
      if (response?.status === "CANCELLED") {
        setState("cancelled");
        setRequestStatus("Investigation cancelled by the operator. No partial evidence was displayed.");
      } else {
        setState("error");
        const message = error instanceof Error ? error.message : String(error);
        setErrorMessage(message);
        setRequestStatus(`Investigation failed: ${message}`);
      }
    } finally {
      if (activeRequestId.current === requestId) activeRequestId.current = null;
    }
  }, []);

  async function decideMembershipFollowUp(decision: "AUTHORIZE_SYNTHETIC_READ" | "DENY"): Promise<void> {
    const proposal = membershipConflictProposal(evidence);
    const request = lastRequest.current;
    if (!proposal || !request || followUpState === "loading") return;
    const requestId = uniqueId();
    activeRequestId.current = requestId;
    setFollowUpState("loading");
    setFollowUpStatus(decision === "DENY"
      ? "Recording the denial. The proposed MCP read will not be sent."
      : "Rechecking the proposal against current MCP semantics, then requesting the exact bounded reads from the synthetic peer.");
    try {
      const result = await api<P2EvidenceEnvelope | { readonly status: "DENIED"; readonly read_executed: false; readonly decision_audit: Record<string, unknown> }>("/api/reference/follow-up", {
        method: "POST",
        headers: { "X-Fabintel-Request-ID": requestId },
        body: JSON.stringify({ decision, candidate: proposal, request }),
      });
      if (result.status === "DENIED") {
        setFollowUpState("denied");
        setFollowUpStatus(`Denied; no MCP read was executed. Decision audit ${String(result.decision_audit.correlation_id ?? "recorded")}.`);
      } else {
        setEvidence(result);
        setSelection(null);
        setFollowUpState("complete");
        const integration = result.provenance.mcp_integration as Record<string, unknown> | undefined;
        const followUp = integration?.follow_up as Record<string, unknown> | undefined;
        const targetWaferIds = Array.isArray(proposal.target_wafer_ids)
          ? proposal.target_wafer_ids.filter((item): item is string => typeof item === "string") : [];
        const refreshedAssessment = summarizeMembershipRefresh(result, targetWaferIds).join(" ");
        setFollowUpStatus(`Authorized synthetic bounded reads completed; evidence was refreshed. ${String(followUp?.status ?? "Review the updated relationship state and audit references below.")} ${refreshedAssessment}`);
      }
    } catch (error) {
      setFollowUpState("error");
      const message = error instanceof Error ? error.message : String(error);
      setFollowUpStatus(`Follow-up failed without replacing current evidence: ${message}`);
    } finally {
      if (activeRequestId.current === requestId) activeRequestId.current = null;
    }
  }

  function startInvestigation(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    try {
      if (!options) throw new Error("Synthetic source options are still loading.");
      if (!selectedTargets.length) throw new Error("Select at least one source-observed abnormal wafer.");
      if (!selectedCohort.length) throw new Error("Select at least one observation cohort member.");
      if (!selectedTargets.every(id => selectedCohort.includes(id))) throw new Error("Every abnormal target must remain in the comparison cohort.");
      if (!scopeId || !scopeOptions.includes(scopeId)) throw new Error("Select an equipment identity returned by the MCP source read.");
      const startUtc = utcTimestamp(start);
      const endUtc = utcTimestamp(end);
      if (Date.parse(endUtc) <= Date.parse(startUtc)) throw new Error("The investigation end must be after the start.");
      const suspectedExposure = {
        [scopeType]: scopeId,
        start: startUtc,
        end: endUtc,
      };
      void submit({
        target_wafer_ids: selectedTargets,
        cohort_wafer_ids: selectedCohort,
        time_window: { start: startUtc, end: endUtc },
        suspected_exposure: suspectedExposure,
        mock_peer_delay_ms: mockPeerDelay,
      });
    } catch (error) {
      setState("error");
      setEvidence(undefined);
      setErrorMessage(error instanceof Error ? error.message : String(error));
      setRequestStatus(error instanceof Error ? error.message : String(error));
    }
  }

  async function cancelInvestigation(): Promise<void> {
    const requestId = activeRequestId.current;
    if (!requestId) return;
    setRequestStatus("Requesting cancellation from the local MCP workflow; waiting for the active bounded read to stop.");
    try {
      await api("/api/cancel", { method: "POST", body: JSON.stringify({ request_id: requestId }) });
    } catch (error) {
      setRequestStatus(error instanceof Error ? error.message : String(error));
    }
  }

  function inspectEvidence(reference: P2EvidenceReference): void {
    setSelection({ reference, details: evidenceDetails(evidence, reference) });
    document.querySelector("#p2-source-inspector")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  const followUpProposal = membershipConflictProposal(evidence);

  return (
    <>
      <header className="reference-header">
        <div className="reference-header-inner">
          <small>FAB INTELLIGENCE · P2 · LOCAL SYNTHETIC RUNNER</small>
          <h1>Process Forensics investigation</h1>
          <p>React contribution mounted in the product-neutral local reference host.</p>
        </div>
      </header>
      <main className="wrap reference-layout">
        <p className="banner" role="note"><strong>Synthetic protocol mode.</strong> Source semantics, permissions, and rows come from the local mock MCP peer. This is not company authorization or company manufacturing evidence.</p>
        <section className="panel" aria-labelledby="request-heading" ref={formRef}>
          <h2 id="request-heading">Choose an investigation</h2>
          <p className="muted">Options below were discovered and read from the configured mock peer. Select a target population, exact equipment scope, and suspected exposure interval. Times entered here use this browser’s local timezone ({Intl.DateTimeFormat().resolvedOptions().timeZone}) and are sent to MCP as UTC. Source reads remain bounded to the synthetic day so outcome observations and complete journey context remain available.</p>
          {optionError ? <p className="status" data-kind="error" role="alert">{optionError} <button type="button" onClick={() => window.location.reload()}>Retry source options</button></p> : null}
          {options ? <form onSubmit={startInvestigation}>
            <div className="reference-form-grid">
              <label>Abnormal wafer targets
                <select aria-label="Abnormal wafer targets" multiple size={Math.min(5, Math.max(2, options.abnormal_wafer_ids.length))} value={selectedTargets} onChange={event => setSelectedTargets(selectedValues(event.currentTarget))}>
                  {options.abnormal_wafer_ids.map(id => <option key={id} value={id}>{id} · source outcome ABNORMAL</option>)}
                </select>
              </label>
              <label>Observed comparison cohort
                <select aria-label="Observed comparison cohort" multiple size={Math.min(5, Math.max(2, options.cohort_wafer_ids.length))} value={selectedCohort} onChange={event => setSelectedCohort(selectedValues(event.currentTarget))}>
                  {options.cohort_wafer_ids.map(id => <option key={id} value={id}>{id}</option>)}
                </select>
              </label>
              <label>Equipment identity type
                <select value={scopeType} onChange={event => {
                  const next = event.currentTarget.value as "chamber_id" | "tool_id";
                  setScopeType(next);
                  const nextIds = next === "chamber_id" ? options.chamber_ids : options.tool_ids;
                  setScopeId(nextIds[0] ?? "");
                }}>
                  <option value="chamber_id">Exact chamber</option>
                  <option value="tool_id">Equipment level</option>
                </select>
              </label>
              <label>{scopeType === "chamber_id" ? "Exact chamber" : "Exact equipment"}
                <select value={scopeId} onChange={event => setScopeId(event.currentTarget.value)}>
                  {scopeOptions.map(id => <option key={id} value={id}>{id}</option>)}
                </select>
              </label>
              <label>Suspected exposure interval start (browser local)
                <input type="datetime-local" value={start} onChange={event => setStart(event.currentTarget.value)} step={60} required />
              </label>
              <label>Suspected exposure interval end (browser local)
                <input type="datetime-local" value={end} onChange={event => setEnd(event.currentTarget.value)} step={60} required />
              </label>
              <label>Mock peer delay for cancellation check (milliseconds)
                <input type="number" min={0} max={1000} step={100} value={mockPeerDelay} onChange={event => setMockPeerDelay(Number(event.currentTarget.value))} />
              </label>
            </div>
            <p className="muted">The selected scope is an operator-supplied investigation question. A caller label or time overlap is not proof of maintenance, exposure, or cause. Missing source coverage remains unknown.</p>
            <div className="actions">
              <button className="primary" type="submit" disabled={state === "loading" || !options.abnormal_wafer_ids.length}>Run seven-source investigation</button>
              {state === "error" || state === "cancelled" ? <button type="button" onClick={() => { if (lastRequest.current) void submit(lastRequest.current); }}>Retry last request</button> : null}
            </div>
          </form> : <p className="status" role="status">Connecting to the synthetic MCP option reads…</p>}
          <p className="status" role="status" aria-live="polite">{requestStatus}</p>
          {options?.onboarding ? <p className="status" role="status">Synthetic onboarding review {options.onboarding.decision} for proposal {options.onboarding.proposal_sha256.slice(0, 12)}. This fixture-only record grants no company permission.</p> : null}
          {options ? <details><summary>Discovery, mapping review, and audited source reads</summary><pre>{JSON.stringify({ protocol_version: options.protocol_version, mode: options.mode, sources: options.sources, onboarding: options.onboarding, audited_reads: options.audited_reads, mock_peer_permission_enforced: options.mock_peer_permission_enforced }, null, 2)}</pre></details> : null}
        </section>

        {followUpProposal || followUpState !== "idle" ? <section className="panel" aria-labelledby="follow-up-heading">
          <h2 id="follow-up-heading">Proposed membership verification</h2>
          {followUpProposal ? <>
            <p className="muted">This exact, source-linked read is a proposal. P2 does not execute it automatically. Authorizing here applies only to the local synthetic peer and is not a company permission or approval.</p>
            <details>
              <summary>Review the exact target, sources, relationships, keys, and time scope</summary>
              <pre>{JSON.stringify({
                target_wafer_ids: followUpProposal.target_wafer_ids,
                step_instance_refs: followUpProposal.step_instance_refs,
                material_relationship_refs: followUpProposal.material_relationship_refs,
                source_relationships: followUpProposal.source_relationships,
                time_window: lastRequest.current?.time_window,
                proposed_not_executed: followUpProposal.proposed_not_executed,
                authorization_status: followUpProposal.authorization_status,
              }, null, 2)}</pre>
            </details>
            <div className="actions">
              <button type="button" className="primary" disabled={followUpState === "loading" || state === "loading"} onClick={() => { void decideMembershipFollowUp("AUTHORIZE_SYNTHETIC_READ"); }}>Authorize exact synthetic read</button>
              <button type="button" disabled={followUpState === "loading" || state === "loading"} onClick={() => { void decideMembershipFollowUp("DENY"); }}>Deny; do not read</button>
            </div>
          </> : <p className="muted">The original read proposal is no longer active. Review the explicit refreshed membership assessment and its MCP audit references below.</p>}
          {followUpStatus ? <p className="status" role="status" aria-live="polite">{followUpStatus}</p> : null}
        </section> : null}

        <P2ProcessForensicsPanels
          state={state}
          {...(evidence ? { evidence } : {})}
          {...(errorMessage ? { errorMessage } : {})}
          onCancel={() => { void cancelInvestigation(); }}
          onRetry={() => { if (lastRequest.current) void submit(lastRequest.current); }}
          onStartInvestigation={() => formRef.current?.scrollIntoView({ behavior: "smooth", block: "start" })}
          onExportEvidence={downloadEvidence}
          onInspectEvidence={inspectEvidence}
          className="p2-reference-panels"
        />

        <section className="panel" id="p2-source-inspector" aria-labelledby="source-inspector-title" aria-live="polite">
          <h2 id="source-inspector-title">Selected evidence provenance</h2>
          {selection ? <>
            <p>{selection.reference.recordId ? `Record ${selection.reference.recordId} · ` : ""}{selection.reference.sourceId ?? "source not specified"}{selection.reference.relationshipId ? ` · ${selection.reference.relationshipId}` : ""}</p>
            {selection.details.length ? <pre>{JSON.stringify(selection.details, null, 2)}</pre> : <p className="muted">The selected reference is retained in the evidence envelope; no matching detail row was found in the mounted source tables.</p>}
          </> : <p className="muted">Use an “Inspect evidence” table action to review the source, relationship, and record references behind a displayed row.</p>}
        </section>
      </main>
    </>
  );
}

createRoot(root).render(<ReferenceHost />);
