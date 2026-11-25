# Scientific algorithms and critical decision rules — FAB Process Forensics

## Exact event-graph scientific workflow

**F1 Semantics/identity:** fetch approved objects and relationship definitions with effective-time windows and cardinalities. A cross-source wafer identity mapping must cover the full event-time uncertainty interval; if the interval crosses its effective boundary, refuse the merge. Represent wafer, lot, process-step *instance*, operation definition, route version, recipe version, equipment and chamber as separate types. No implicit equivalence between different namespaced IDs.

**F2 Event normalization:** preserve event time versus record-ingestion time, timezone, uncertainty interval, source version and ordering ties. Only the relationship-authorized process event time controls chronology and exposure; record-ingestion time remains a separate displayed attribute and cannot move an event into or out of a query window. Split/merge and lot-membership changes are time-scoped edges, not timeless attributes. An edge that overlaps an event's clock-uncertainty interval is a possible relationship; a membership change inside that interval remains ambiguous. Rework creates a new step instance even if the operation code matches. Every graph link stores its approval evidence.

**F3 Exact history:** assemble a minimal valid path for each wafer and trace supported multi-hop lot lineage only across source-declared, effective-dated `SPLIT_FROM`/`MERGED_FROM` lot edges. Preserve seed and edge provenance, direction, and uncertainty; do not traverse lot membership into sibling wafers. Distinguish observed fact, possible edge, and missing relationship. Reconstruction completeness may be reported relative only to a *verified* expected route; unknown route details cannot yield a precise percentage.

Route conformance also requires a source-linked route-definition relationship that authorizes the approval marker, route identity/version, and ordered operations. Its effectivity must contain each compared event's full time-uncertainty interval. A caller label alone cannot make a route definition verified; missing or time-ambiguous definition evidence leaves conformance unestablished.

**F4 Exposure predicates:** define events by one explicit chamber or exact tool ID, process-step instance and time, with known processing start/end where available. Apply separate exposure modes: processed by actual chamber; processed by an exact tool; potential exposure with missing selected-equipment assignment; not observed exposed under complete coverage. No inference of chamber from tool or equipment group; no assumption that time overlap demonstrates contact with a condition.

Source relationships must be effective across the full event-time uncertainty interval before an event can establish exact exposure or an observed nonmatch. If the nominal timestamp is valid but its uncertainty crosses a relationship effectivity boundary, that wafer remains `UNKNOWN` for the exposure query and cannot enter the unexposed comparator set.

When actual processing start/end bounds are supplied, the relationship must also cover the complete independently uncertain processing interval. A timestamp inside relationship effectivity does not qualify a process interval whose possible start or end falls outside it; affected wafers remain `UNKNOWN` and are excluded from nonmatch comparators.

Equipment confounder strata use only fields declared by the event relationship and effective across the event-time uncertainty interval; boundary-ambiguous window matches are kept out of exact strata and disclosed as uncertain context.

**F5 Process mining:** build a conventional time-ordered variant baseline, then challenge it with object-centric mining on rework/split-merge fixtures. Accept advanced engine only if path correctness, runtime or useful discovery measurably improves under the same oracle.

**F6 Hypothesis challenge:** for each explanation, construct its support set, counterexamples, comparator cohort, missing data and alternative explanations. Explicitly search normal wafers with the suspected exposure and abnormal wafers without it. Present alternative sources and identifiability limitations.

Route patterns are included in B05 as source-linked descriptive context alongside outcome and exposure groups. A route mismatch is emitted only where the actual route fields, expected definition, effective interval, and observation coverage are verified. Missing route history remains unclassified. Route pattern counts do not rank explanations or establish association or causality.

**F7 Output:** immutable evidence paths with source IDs, typed step IDs, bounded query audit, ordering uncertainty, negative evidence and reviewer-oriented graph/timeline/tabular equivalents. LLM cannot add edges or facts outside the verified envelope.

**Preferred OSS** NetworkX/rustworkx for basic graph methods (benchmark), DuckDB for bounded read-only in synthetic harness, ocel-mine or similar permissive object-centric engine only if justified, CORE-T/schemagraph only as challenged retrieval implementations. Existing governed semantic MCP wins ties.


## Minimum correct implementation order
A. Validate source/identity/units/permissions BEFORE scientific analysis. B. Implement an independently understandable deterministic baseline and a fixed positive/negative oracle. C. Create an evidence envelope and show a complete user workflow. D. Add the full required scientific methods with assumption diagnostics and falsifying cases. E. Compare advanced OSS only where it can beat or materially extend that baseline; freeze test cases first. F. Run the combined product and real target-OS/offline qualification. G. Repeat audit until all gates pass.

## Mathematical and evaluation requirements
- For numeric estimates, specify the estimand, unit, effective independent sample, uncertainty method, algorithm/version and declared applicability domain.
- For classification, retrieval and anomaly cases, precommit held-out metrics, precision/recall/calibration or appropriately justified equivalents. Never fit thresholds to evaluation answers.
- Use group/time/device/wafer/lot/experiment-aware holdouts where dependencies require them; random measurement-row splits are not acceptable evidence of broader generalization.
- Distinguish data observed, data estimated and data unknown; refuse if physical constraints or study assumptions cannot be verified.
- Run property, metamorphic, adversarial and counterfactual *tests* where meaningful (e.g. changing labels must not create a spurious causal claim; adding an unapproved join must trigger refusal).
- An LLM explanation must be mechanically checked against the verified evidence object. An independent code-based oracle, not an agent's agreement, determines scientific pass/fail.

## Scientific peer review rubric
Engineer/reviewer should be able to answer: Is the population actually eligible? What was the measured unit and its grain? Which approved sources and joins were used? Could sampling or timing explain the observation? Is the statistical estimand identifiable? Which alternative explanations were tested? Which result is observed rather than predicted? What result would invalidate the conclusion? Does the method generalize to unseen wafers/lots/tools/periods? What is explicitly unknown?
