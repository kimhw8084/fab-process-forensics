/** Reusable P2 evidence panels for the shared FAB Intelligence host. */
const element = (tag, text, className) => {
  const node = document.createElement(tag);
  if (text !== undefined && text !== null) node.textContent = String(text);
  if (className) node.className = className;
  return node;
};

function jsonBlock(parent, label, value) {
  parent.append(element('h4', label));
  const pre = element('pre', JSON.stringify(value, null, 2));
  parent.append(pre);
}

function table(parent, captionText, headings, rows) {
  const pageSize = 100;
  let page = 0;
  const view = element('table');
  view.append(element('caption', captionText));
  const thead = element('thead');
  const header = element('tr');
  for (const heading of headings) {
    const cell = element('th', heading);
    cell.setAttribute('scope', 'col');
    header.append(cell);
  }
  thead.append(header);
  view.append(thead);
  const tbody = element('tbody');
  view.append(tbody);
  const wrapper = element('div', undefined, 'scroll');
  wrapper.append(view);
  let controls;
  let pageStatus;
  let previous;
  let next;
  if (rows.length > pageSize) {
    controls = element('nav', undefined, 'table-page-controls');
    controls.setAttribute('aria-label', `Page controls for ${captionText}`);
    pageStatus = element('span', '', 'table-page-status');
    pageStatus.setAttribute('role', 'status');
    pageStatus.setAttribute('aria-live', 'polite');
    previous = element('button', 'Previous rows');
    previous.type = 'button';
    next = element('button', 'Next rows');
    next.type = 'button';
    controls.append(pageStatus, previous, next);
    previous.addEventListener('click', () => { page -= 1; drawPage(); });
    next.addEventListener('click', () => { page += 1; drawPage(); });
  }
  function drawPage() {
    const pageCount = Math.max(1, Math.ceil(rows.length / pageSize));
    page = Math.max(0, Math.min(page, pageCount - 1));
    const start = page * pageSize;
    tbody.replaceChildren();
    for (const values of rows.slice(start, start + pageSize)) {
      const row = element('tr');
      for (const value of values) row.append(element('td', value ?? 'Unknown'));
      tbody.append(row);
    }
    if (pageStatus) {
      pageStatus.textContent = `Rows ${start + 1}–${Math.min(start + pageSize, rows.length)} of ${rows.length}`;
      previous.disabled = page === 0;
      next.disabled = page + 1 >= pageCount;
    }
  }
  drawPage();
  if (controls) parent.append(controls);
  parent.append(wrapper);
}

function section(parent, title) {
  const heading = element('h3', title);
  parent.append(heading);
  return heading;
}

function memberSummary(ids, emptyLabel = 'No observed members') {
  const values = Array.isArray(ids) ? ids : [];
  if (!values.length) return emptyLabel;
  const sample = values.slice(0, 6).join(', ');
  return `${values.length} member(s) · sample ${sample}${values.length > 6 ? ' …' : ''}`;
}

function lotEvidenceAtEvent(step) {
  const eventLot = step.lot_id_at_event || 'Unknown';
  const state = step.membership_state;
  if (state !== 'CONFLICTS_WITH_EVENT_ROW_LOT_ID') {
    if (!state) return eventLot;
    const label = state === 'SOURCE_LINKED_TIME_SCOPED_MEMBERSHIP'
      ? 'source-linked membership'
      : state.replaceAll('_', ' ').toLowerCase();
    return `${eventLot} · ${label}`;
  }

  const lineage = step.lot_lineage || {};
  const conflicts = (lineage.missing_evidence || []).filter(item =>
    item?.reason === 'EVENT_LOT_ID_CONFLICTS_WITH_TIME_SCOPED_MEMBERSHIP');
  const candidateLots = [...new Set(conflicts.flatMap(item => item.candidate_lot_ids || []))];
  const membershipRecords = [...new Set((lineage.seeds || []).flatMap(seed => seed.provenance || [])
    .map(item => item.material_relationship_id).filter(Boolean))];
  const membership = candidateLots.join(', ') || 'unresolved';
  const records = membershipRecords.length ? ` · membership record ${membershipRecords.join(', ')}` : '';
  return `CONFLICT · event row ${eventLot}; time-scoped membership ${membership}${records}`;
}

/** Return evidence-backed panel data for a host's native component library. */
export function buildP2PanelModels(evidenceEnvelope) {
  if (!evidenceEnvelope || typeof evidenceEnvelope !== 'object' || Array.isArray(evidenceEnvelope)) {
    throw new TypeError('A P2 evidence envelope object is required.');
  }
  const transformations = Array.isArray(evidenceEnvelope.transformations) ? evidenceEnvelope.transformations : [];
  const artifacts = Array.isArray(evidenceEnvelope.artifacts) ? evidenceEnvelope.artifacts : [];
  const journey = transformations.find(item => item?.id === 'p2-journey-and-route-variants-v1') || null;
  const snapshot = artifacts.find(item => item?.kind === 'investigation_snapshot') || null;
  return {
    summary: {
      status: evidenceEnvelope.status || 'UNKNOWN',
      investigation_id: evidenceEnvelope.investigation_id || null,
      claims: Array.isArray(evidenceEnvelope.claims) ? evidenceEnvelope.claims : [],
      limitations: Array.isArray(evidenceEnvelope.limitations) ? evidenceEnvelope.limitations : [],
    },
    journey: {
      transformation: journey,
      journeys: Array.isArray(journey?.journeys) ? journey.journeys : [],
      route_variants: Array.isArray(journey?.route_variants) ? journey.route_variants : [],
      route_population_summary: journey?.route_population_summary || null,
    },
    exposure: {
      populations: Array.isArray(evidenceEnvelope.populations) ? evidenceEnvelope.populations : [],
      analysis: snapshot?.exposure_analysis || null,
    },
    counterevidence: {
      investigations: Array.isArray(evidenceEnvelope.counterevidence) ? evidenceEnvelope.counterevidence : [],
    },
    evidence: {
      sources: Array.isArray(evidenceEnvelope.sources) ? evidenceEnvelope.sources : [],
      snapshot,
      uncertainty: evidenceEnvelope.uncertainty || {},
      limitations: Array.isArray(evidenceEnvelope.limitations) ? evidenceEnvelope.limitations : [],
      input_sha256: evidenceEnvelope.provenance?.input_sha256 || null,
    },
  };
}

export function renderP2Summary(root, result) {
  root.replaceChildren();
  root.classList.remove('empty');
  const status = element('span', result.status, `pill ${result.status}`);
  const heading = element('p');
  heading.append(status, document.createTextNode(`  Investigation ${result.investigation_id}`));
  root.append(heading);

  const sectionNav = element('nav', undefined, 'investigation-section-nav');
  sectionNav.setAttribute('aria-label', 'Investigation section navigation');
  sectionNav.append(element('span', 'Jump to:'));
  for (const [label, target] of [
    ['Wafer journey and routes', 'journey-title'],
    ['Exposure populations', 'exposure-title'],
    ['Counterevidence', 'counter-title'],
    ['Sources and evidence', 'sources-title'],
  ]) {
    const link = element('a', label);
    link.href = `#${target}`;
    sectionNav.append(link);
  }
  root.append(sectionNav);

  const transformations = result.transformations || [];
  const journeyResult = transformations.find(item => item.id === 'p2-journey-and-route-variants-v1');
  const journeys = journeyResult?.journeys || [];
  const snapshot = (result.artifacts || []).find(item => item.kind === 'investigation_snapshot');
  const exposure = snapshot?.exposure_analysis || {};
  const scope = snapshot?.scope || {};
  const chronologyUncertain = journeys.filter(journey => (journey.steps || []).some(step => step.order_uncertain_with?.length)).length;
  const reworkInstances = journeys.reduce((total, journey) => total + (journey.rework_edges || []).length, 0);
  const stepCount = journeys.reduce((total, journey) => total + (journey.steps || []).length, 0);
  const routeCounts = result.uncertainty?.route_conformance_counts || {};
  const causalStatus = result.counterevidence?.[0]?.causal_conclusion?.status || 'NOT_ESTABLISHED';
  const nextCheck = result.counterevidence?.[0]?.next_authorized_verification?.purpose || 'No next verification was returned.';
  const rows = [
    ['Abnormal target wafers', Array.isArray(scope.target_wafer_ids) ? scope.target_wafer_ids.length : 'Not declared'],
    ['Cohort population', Array.isArray(exposure.population) ? exposure.population.length : 'Not available'],
    ['Observed journeys / step instances', `${journeys.length} / ${stepCount}`],
    ['Histories with chronology ambiguity', chronologyUncertain],
    ['Explicit rework edges', reworkInstances],
    ['Observed route variants', (journeyResult?.route_variants || []).length],
    ['Route conformance counts', Object.entries(routeCounts).map(([key, value]) => `${key}: ${value}`).join(' · ') || 'Not established'],
    ['Exact / potential / unknown exposure', `${(exposure.definitely_exposed || []).length} / ${(exposure.potentially_exposed || []).length} / ${(exposure.unknown || []).length}`],
    ['Verified unexposed comparators', (exposure.verified_unexposed || []).length],
    ['History / exposure coverage', `${exposure.history_coverage_status || journeys[0]?.history_coverage?.coverage_evidence_level || 'UNKNOWN'} / ${exposure.coverage_evidence_level || 'UNKNOWN'}`],
    ['Causal conclusion', causalStatus],
  ];
  table(root, 'Investigation cohort triage and evidence coverage', ['Measure', 'Observed'], rows);
  root.append(element('p', `Proposed next verification · authorization must be confirmed by the configured MCP server: ${nextCheck}`));

  const claimDetails = element('details');
  claimDetails.append(element('summary', `Inspect all ${result.claims?.length || 0} descriptive and evidence claims`));
  if (result.claims?.length) {
    table(claimDetails, 'Claims retained in the evidence envelope', ['Statement', 'Category', 'Certainty', 'Sources'],
      result.claims.map(item => [item.statement, item.category, item.certainty, (item.source_ids || []).join(', ') || 'None']));
  } else {
    claimDetails.append(element('p', 'No positive claim was returned.'));
  }
  root.append(claimDetails);
}

function renderJourneyCard(root, journey) {
    root.append(element('h3', `Wafer ${journey.wafer_id} · ${journey.history_status.replaceAll('_', ' ')} · ${journey.route_conformance.replaceAll('_', ' ')}`));
    table(root, `Chronological process step instances for wafer ${journey.wafer_id}`,
      ['Step instance', 'Operation / definition', 'Event time / clock', 'Route / version', 'Lot evidence at event', 'Tool / chamber', 'Source / relationship'],
      (journey.steps || []).map(step => [
        step.step_instance_id,
        `${step.operation} · ${step.operation_definition_id || step.operation_definition_status}`,
        `${step.timestamp}${step.recorded_at ? ` · recorded ${step.recorded_at}` : ''}${step.time_uncertainty_seconds ? ` · ±${step.time_uncertainty_seconds}s` : ''}${step.order_uncertain_with?.length ? ` · unordered with ${step.order_uncertain_with.join(', ')}` : ''}`,
        [step.route_id, step.route_version].filter(Boolean).join(' / ') || 'Unknown',
        lotEvidenceAtEvent(step),
        [step.tool_id, step.chamber_id].filter(Boolean).join(' / ') || 'Unknown',
        `${step.source_id || 'No source ID'} / ${step.relationship_id || 'No relationship record'}`,
      ]));
    const lineagePaths = journey.lot_lineage_paths || [];
    if (lineagePaths.length) {
      table(root, `Source-declared lot lineage paths for wafer ${journey.wafer_id}`,
        ['Step instance', 'Start lot', 'Related lot', 'Status', 'Relationship path'],
        lineagePaths.map(path => [
          path.step_instance_id,
          path.start_lot_id,
          path.end_lot_id,
          path.status,
          (path.relationships || []).map(edge => `${edge.relationship_type} ${edge.record_id} (${edge.traversal_direction})`).join(' → '),
        ]));
    }
    const details = element('details');
    details.append(element('summary', 'Inspect route segments, rework, membership, and material-edge provenance'));
    jsonBlock(details, 'Route segments', journey.route_segments || []);
    jsonBlock(details, 'History coverage', journey.history_coverage || {});
    jsonBlock(details, 'Explicit rework edges', journey.rework_edges || []);
    jsonBlock(details, 'Time scoped material relationships', journey.material_relationships || []);
    jsonBlock(details, 'Time scoped lot lineage paths and missing evidence', {
      paths: lineagePaths,
      per_step: (journey.steps || []).map(step => ({
        step_instance_id: step.step_instance_id,
        membership_state: step.membership_state,
        lineage: step.lot_lineage || {},
      })),
    });
    root.append(details);
}

export function renderP2Journey(root, result) {
  root.replaceChildren();
  root.classList.remove('empty');
  const transform = (result.transformations || []).find(item => item.id === 'p2-journey-and-route-variants-v1');
  if (!transform) {
    root.append(element('p', 'No journey was produced.'));
    return;
  }
  const journeys = transform.journeys || [];
  const pageSize = 10;
  let page = 0;
  const controls = element('div', undefined, 'journey-controls');
  const searchLabel = element('label', 'Find wafer journey by ID');
  const search = element('input');
  search.type = 'search';
  search.id = 'p2-journey-search';
  search.setAttribute('aria-label', 'Find wafer journey by ID');
  search.placeholder = 'Enter a wafer ID';
  searchLabel.htmlFor = search.id;
  searchLabel.append(search);
  const pageStatus = element('p', '', 'journey-page-status');
  pageStatus.setAttribute('role', 'status');
  pageStatus.setAttribute('aria-live', 'polite');
  const previous = element('button', 'Previous 10 journeys');
  previous.type = 'button';
  previous.disabled = true;
  const next = element('button', 'Next 10 journeys');
  next.type = 'button';
  const pageButtons = element('div', undefined, 'journey-page-buttons');
  pageButtons.append(previous, next);
  controls.append(searchLabel, pageStatus, pageButtons);
  const pageContent = element('div', undefined, 'journey-page-content');
  root.append(controls, pageContent);

  const drawPage = () => {
    const query = search.value.trim().toLocaleLowerCase();
    const filtered = journeys.filter(journey => String(journey.wafer_id).toLocaleLowerCase().includes(query));
    const pageCount = Math.ceil(filtered.length / pageSize);
    page = Math.max(0, Math.min(page, Math.max(0, pageCount - 1)));
    const start = page * pageSize;
    const visible = filtered.slice(start, start + pageSize);
    pageContent.replaceChildren();
    if (visible.length) {
      for (const journey of visible) renderJourneyCard(pageContent, journey);
    } else {
      pageContent.append(element('p', query ? `No wafer journeys match “${search.value.trim()}”.` : 'No journeys were returned.'));
    }
    pageStatus.textContent = filtered.length
      ? `Showing ${start + 1}–${Math.min(start + pageSize, filtered.length)} of ${filtered.length} ${query ? 'matching ' : ''}wafer journeys.`
      : 'Showing 0 wafer journeys.';
    previous.disabled = page === 0;
    next.disabled = page + 1 >= pageCount;
  };
  search.addEventListener('input', () => { page = 0; drawPage(); });
  previous.addEventListener('click', () => { page -= 1; drawPage(); });
  next.addEventListener('click', () => { page += 1; drawPage(); });
  drawPage();

  section(root, 'Observed route variants');
  for (const [index, variant] of (transform.route_variants || []).entries()) {
    const share = Number.isFinite(variant.share_of_ordered_observed_histories)
      ? ` · ${(variant.share_of_ordered_observed_histories * 100).toFixed(1)}% of ${variant.ordered_observed_history_denominator} ordered observed histories`
      : '';
    const waferIds = Array.isArray(variant.wafer_ids) ? variant.wafer_ids : [];
    root.append(element('p', `${variant.count} wafer(s): ${variant.operations.join(' → ')} · ${waferIds.length} members${waferIds.length ? ` · sample ${waferIds.slice(0, 6).join(', ')}${waferIds.length > 6 ? ' …' : ''}` : ''}${share}`));
    if (waferIds.length > 6) {
      const members = element('details');
      members.append(element('summary', `Inspect all ${waferIds.length} wafers in route variant ${index + 1}`));
      members.append(element('pre', waferIds.join('\n')));
      root.append(members);
    }
  }
  const population = transform.route_population_summary;
  if (population) {
    section(root, 'Route population and denominator');
    const summarizeMembers = ids => {
      const values = Array.isArray(ids) ? ids : [];
      return `${values.length} wafer(s)${values.length ? ` · ${values.slice(0, 6).join(', ')}${values.length > 6 ? ' …' : ''}` : ''}`;
    };
    table(root, 'Observed route histories and separately declared coverage population',
      ['Measure', 'Wafer IDs / count'], [
        ['Coverage status', population.coverage_status],
        ['Declared covered population', summarizeMembers(population.declared_covered_wafer_ids)],
        ['Observed event histories', summarizeMembers(population.observed_event_wafer_ids)],
        ['Ordered observed denominator', summarizeMembers(population.ordered_observed_history_wafer_ids)],
        ['Chronology uncertain', summarizeMembers(population.chronology_uncertain_wafer_ids)],
        ['Declared members with no rows', summarizeMembers(population.declared_covered_wafer_ids_without_event_rows)],
        ['Observed outside declared coverage', summarizeMembers(population.observed_event_wafer_ids_outside_declared_coverage)],
      ]);
    const memberDetails = element('details');
    memberDetails.append(element('summary', 'Inspect complete route-population member sets and denominator evidence'));
    jsonBlock(memberDetails, 'Route-population membership sets', {
      declared_covered_wafer_ids: population.declared_covered_wafer_ids || [],
      observed_event_wafer_ids: population.observed_event_wafer_ids || [],
      ordered_observed_history_wafer_ids: population.ordered_observed_history_wafer_ids || [],
      chronology_uncertain_wafer_ids: population.chronology_uncertain_wafer_ids || [],
      declared_covered_wafer_ids_without_event_rows: population.declared_covered_wafer_ids_without_event_rows || [],
      observed_event_wafer_ids_outside_declared_coverage: population.observed_event_wafer_ids_outside_declared_coverage || [],
    });
    root.append(memberDetails);
    root.append(element('p', population.meaning));
  }
  root.append(element('p', 'These are observed sequences. Missing events are not treated as route violations.'));
}

export function renderP2Exposure(root, result) {
  root.replaceChildren();
  root.classList.remove('empty');
  const groups = result.populations || [];
  if (!groups.length) {
    root.append(element('p', 'No equipment exposure window was supplied.'));
    return;
  }
  const artifact = (result.artifacts || []).find(item => item.kind === 'investigation_snapshot')?.exposure_analysis;
  const grid = element('div', undefined, 'two');
  for (const group of groups) {
    const card = element('div', undefined, 'population');
    const waferIds = Array.isArray(group.wafer_ids) ? group.wafer_ids : [];
    card.append(element('h3', group.classification.replaceAll('_', ' ')), element('div', `${group.count} wafer(s)`));
    card.append(element('p', waferIds.length ? `${waferIds.slice(0, 5).join(', ')}${waferIds.length > 5 ? ` · and ${waferIds.length - 5} more` : ''}` : 'None'));
    card.append(element('small', group.basis));
    if (waferIds.length > 5) {
      const members = element('details');
      members.append(element('summary', `Inspect all ${waferIds.length} ${group.classification.replaceAll('_', ' ').toLowerCase()} wafer IDs`));
      members.append(element('pre', waferIds.join('\n')));
      card.append(members);
    }
    grid.append(card);
  }
  root.append(grid);
  if (!artifact) return;
  root.append(element('p', `${artifact.scope_type} ${artifact.scope_id} · [${artifact.window.start}, ${artifact.window.end})`));
  const context = artifact.condition_context || { condition_type: 'UNSPECIFIED', evidence_status: 'NOT_SUPPLIED' };
  root.append(element('p', `Caller-supplied interval label: ${context.condition_type} · ${context.evidence_status.replaceAll('_', ' ').toLowerCase()}`));
  const unknownMembers = new Set(groups.filter(group => group.classification === 'UNKNOWN').flatMap(group => group.wafer_ids || []));
  if (unknownMembers.size) {
    const journeyTransform = (result.transformations || []).find(item => item.id === 'p2-journey-and-route-variants-v1');
    const journeyByWafer = new Map((journeyTransform?.journeys || []).map(item => [item.wafer_id, item]));
    const relationshipUncertain = new Map();
    for (const row of artifact.evidence || []) {
      if (!unknownMembers.has(row.wafer_id) || ![
        'SCOPE_OR_TIME_FIELD_NOT_APPROVED_BY_RELATIONSHIP', 'SOURCE_RELATIONSHIP_EFFECTIVITY_UNCERTAIN',
      ].includes(row.classification)) continue;
      const refs = relationshipUncertain.get(row.wafer_id) || [];
      refs.push({ step_instance_id: row.step_instance_id, classification: row.classification, source_id: row.source_id, relationship_id: row.relationship_id });
      relationshipUncertain.set(row.wafer_id, refs);
    }
    const withoutHistory = [...unknownMembers].filter(waferId => !journeyByWafer.has(waferId) && !relationshipUncertain.has(waferId)).sort();
    const relationshipUnknown = [...relationshipUncertain.keys()].sort();
    const observedNonmatchUnknown = [...unknownMembers].filter(waferId => !relationshipUncertain.has(waferId) && !withoutHistory.includes(waferId)).sort();
    const reasonGroups = [
      {
        reason: 'Required source relationship or time effectivity unresolved',
        members: relationshipUnknown,
        basis: 'A source-linked event exists, but the declared equipment/time relationship cannot support exact classification.',
      },
      {
        reason: 'No process-history rows in this snapshot',
        members: withoutHistory,
        basis: 'No process step was submitted for these members; missing rows are not proof of nonexposure.',
      },
      {
        reason: 'No selected-window match observed under incomplete coverage',
        members: observedNonmatchUnknown,
        basis: `A nonmatching event was not established because exposure coverage is ${artifact.coverage_evidence_level || 'UNKNOWN'}; these members are not verified-unexposed comparators.`,
      },
    ].filter(group => group.members.length);
    section(root, 'Why exposure remains unknown');
    table(root, 'Unknown exposure reasons without converting missing records into negative evidence',
      ['Reason', 'Wafer count', 'Example members', 'Evidence boundary'],
      reasonGroups.map(group => [group.reason, group.members.length, `${group.members.slice(0, 8).join(', ')}${group.members.length > 8 ? ' …' : ''}`, group.basis]));
    const detail = element('details');
    detail.append(element('summary', `Inspect all unknown-member IDs and source-linked uncertainty (${unknownMembers.size} wafers)`));
    jsonBlock(detail, 'Unknown exposure reason groups', reasonGroups.map(group => ({ ...group, relationship_evidence: group.members.flatMap(waferId => relationshipUncertain.get(waferId) || []) })));
    root.append(detail);
  }
  section(root, 'Source-linked records used for exposure classification');
  root.append(element('p', 'An exact match requires the source-declared equipment field and event-time uncertainty to support the selected scope. Possible and unknown records are retained with their reason; they are not upgraded to confirmed exposure. Population nonmatches are usable as verified-unexposed comparators only under SOURCE_VERIFIED coverage.'));
  const classificationMeaning = {
    EXACT_CHAMBER_WINDOW_MATCH: 'Source-linked exact chamber and event time match.',
    EXACT_TOOL_WINDOW_MATCH: 'Source-linked exact tool and event time match.',
    UNKNOWN_CHAMBER: 'The process record does not identify the selected chamber.',
    UNKNOWN_TOOL: 'The process record does not identify the selected tool.',
    TIME_BOUNDARY_UNCERTAIN: 'Clock uncertainty crosses the selected window boundary.',
    SCOPE_OR_TIME_FIELD_NOT_APPROVED_BY_RELATIONSHIP: 'The relationship does not declare a required scope or time field.',
    SOURCE_RELATIONSHIP_EFFECTIVITY_UNCERTAIN: 'The relationship is not effective across the full event-time uncertainty interval.',
  };
  table(root, `Source-linked process records used for ${artifact.scope_type} ${artifact.scope_id} classification`,
    ['Wafer', 'Step instance', 'Classification', 'Why this classification applies', 'Event time (UTC)', 'Source / relationship'],
    (artifact.evidence || []).map(item => [item.wafer_id, item.step_instance_id, item.classification, classificationMeaning[item.classification] || 'Inspect the source fields and relationship before interpretation.', item.timestamp_utc || item.timestamp, `${item.source_id || 'Unknown'} / ${item.relationship_id || 'Unknown'}`]));
  const coverageDetails = element('details');
  coverageDetails.append(element('summary', `Inspect ${artifact.coverage_evidence_level || 'UNKNOWN'} coverage membership and provenance`));
  jsonBlock(coverageDetails, 'Coverage record', artifact.coverage_evidence || {});
  root.append(coverageDetails);
  section(root, 'Source linked condition-event context');
  root.append(element('p', (artifact.condition_event_status || 'NO_CONDITION_EVENT_RECORDS_SUPPLIED').replaceAll('_', ' ')));
  if (artifact.condition_event_evidence?.length) {
    table(root, 'Source-linked condition-event time context',
      ['Event', 'Type', 'Exact equipment', 'Time context', 'Time uncertainty', 'Source / relationship'],
      artifact.condition_event_evidence.map(item => [item.condition_event_id, item.condition_type, `${item.equipment_type} ${item.equipment_id}`, item.temporal_context, `${item.time_uncertainty_seconds}s`, `${item.source_id} / ${item.relationship_id}`]));
    root.append(element('p', 'Condition timing is contextual evidence. Overlap alone does not establish exposure effect or root cause.'));
  }
}

function renderVerificationProposals(root, verification) {
  const candidates = Array.isArray(verification?.candidates) ? verification.candidates : [];
  section(root, 'Ranked next authorized checks · proposals only');
  if (!candidates.length) {
    jsonBlock(root, 'Next authorized verification', verification || {});
    return;
  }
  root.append(element('p', verification.selection_rule || 'Order reflects evidence relevance, not causal probability. No check has been executed.'));
  table(root, 'Verification proposals derived from unresolved source-linked evidence',
    ['Rank', 'Check', 'Operation', 'Affected members / information bound', 'Source / relationship', 'Declared keys', 'What it could distinguish'],
    candidates.map(candidate => [
      candidate.rank,
      `${candidate.category}${(candidate.covers_additional_checks || []).map(item => ` + ${item.category}`).join('')} · ${candidate.purpose}`,
      candidate.logical_operation,
      `${candidate.maximum_directly_addressed_members} maximum directly addressed · ${candidate.review_factors?.step_instance_ref_count ?? 0} exact steps · ${candidate.review_factors?.bounded_read_request_count_proxy ?? 0} read-pair proxy · ${candidate.review_factors?.coverage_evidence_level || 'UNKNOWN'} coverage · ${candidate.review_factors?.negative_evidence_interpretation_risk || 'UNASSESSED'} negative-evidence risk · ${candidate.priority_basis} · ${(candidate.target_wafer_ids || []).slice(0, 6).join(', ')}${(candidate.target_wafer_ids || []).length > 6 ? ' …' : ''}`,
      (candidate.source_relationships || []).map(ref => `${ref.source_id} / ${ref.relationship_id}`).join(', ') || 'Not identified',
      (candidate.source_relationships || []).length
        ? candidate.source_relationships.map(ref => `${ref.relationship_id}: ${(ref.requested_declared_keys || []).join(', ') || 'no bounded keys'}`).join(' · ')
        : (candidate.requested_declared_keys || []).join(', ') || 'Semantic review only',
      candidate.distinguishing_value,
    ]));
  const details = element('details');
  details.append(element('summary', 'Inspect full bounded verification proposals and provenance targets'));
  jsonBlock(details, 'Authorization-gated verification proposal', verification);
  root.append(details);
}

export function renderP2Counterevidence(root, result) {
  root.replaceChildren();
  root.classList.remove('empty');
  const investigations = result.counterevidence || [];
  if (!investigations.length) {
    root.append(element('p', 'No outcome rows were supplied; outcome evidence is unavailable.'));
    return;
  }
  for (const item of investigations) {
    root.append(element('p', item.question));
    root.append(element('p', item.interpretation));
    renderVerificationProposals(root, item.next_authorized_verification);
    table(root, 'Outcome and exact-equipment exposure observations',
      ['Wafer', 'Outcome', 'Exposure state', 'Outcome time', 'Source / relationship'],
      (item.outcome_evidence || []).map(outcome => [outcome.wafer_id, outcome.label, outcome.exposure_classification, outcome.timestamp, `${outcome.source_id} / ${outcome.relationship_id}`]));
    section(root, 'Supporting observations');
    table(root, 'Abnormal wafer supporting process instances',
      ['Abnormal wafer', 'Exact process instances'],
      (item.supporting_observations || []).map(record => [record.wafer_id, (record.process_event_refs || []).map(ref => ref.step_instance_id).join(', ')]));
    section(root, 'Contradicting observations');
    jsonBlock(root, 'Normal wafers with the same exact exposure and abnormal wafers without an observed exact exposure', item.contradicting_observations || {});
    section(root, 'Confounders and missingness');
    jsonBlock(root, 'Selection, product mix, time, and equipment context', item.confounders || {});
    const alternatives = item.confounders?.equipment?.alternative_equipment_hypotheses || [];
    section(root, 'Competing equipment patterns');
    if (alternatives.length) {
      table(root, 'Source-verified alternate equipment patterns in the same investigation window',
        ['Equipment', 'Abnormal with event · count / sample', 'Normal with event · count / sample', 'Abnormal without exact event · count / sample', 'Nonmatch coverage'],
        alternatives.map(candidate => [
          `${candidate.equipment_type} ${candidate.equipment_id}`,
          memberSummary(candidate.abnormal_wafers_with_observed_exact_event),
          memberSummary(candidate.normal_wafers_with_observed_exact_event),
          memberSummary(candidate.abnormal_wafers_without_observed_exact_event, 'Not classified'),
          candidate.coverage?.accepted_for_nonmatch_classification ? 'Accepted locally' : 'Incomplete / unknown',
        ]));
      for (const candidate of alternatives) {
        const details = element('details');
        details.append(element('summary', `Inspect ${candidate.equipment_type} ${candidate.equipment_id} evidence and uncertainty`));
        jsonBlock(details, 'Alternative equipment evidence', candidate);
        root.append(details);
      }
    } else {
      root.append(element('p', 'No source-verified alternative equipment pattern was available in this snapshot.'));
    }
    jsonBlock(root, 'Missing or ambiguous evidence', item.missing_or_ambiguous_evidence || {});
    section(root, 'Interpretation status');
    jsonBlock(root, 'Statistical association', item.statistical_association || {});
    jsonBlock(root, 'Proposed explanation', item.proposed_explanation || {});
    jsonBlock(root, 'Causal conclusion', item.causal_conclusion || {});
  }
}

export function renderP2Evidence(root, result) {
  root.replaceChildren();
  root.classList.remove('empty');
  section(root, 'Source records');
  jsonBlock(root, 'Source references', result.sources || []);
  const artifact = (result.artifacts || []).find(item => item.kind === 'investigation_snapshot');
  jsonBlock(root, 'Investigation start scope', artifact?.scope || {});
  jsonBlock(root, 'Target outcome records', artifact?.target_outcomes || []);
  jsonBlock(root, 'Relationship records', artifact?.source_relationships || []);
  jsonBlock(root, 'Uncertainty', result.uncertainty || {});
  section(root, 'Limitations');
  const list = element('ul');
  for (const limitation of result.limitations || []) list.append(element('li', limitation));
  root.append(list);
  root.append(element('p', `Input SHA-256: ${result.provenance?.input_sha256 || 'Unavailable'}`));
}

/** Render reusable product panels into containers supplied by a host shell. */
export function renderP2Contribution(containers, evidenceEnvelope) {
  const required = ['summary', 'journey', 'exposure', 'counterevidence', 'evidence'];
  for (const key of required) {
    if (!(containers[key] instanceof Element)) throw new TypeError(`P2 panel container '${key}' is required.`);
  }
  renderP2Summary(containers.summary, evidenceEnvelope);
  renderP2Journey(containers.journey, evidenceEnvelope);
  renderP2Exposure(containers.exposure, evidenceEnvelope);
  renderP2Counterevidence(containers.counterevidence, evidenceEnvelope);
  renderP2Evidence(containers.evidence, evidenceEnvelope);
}
