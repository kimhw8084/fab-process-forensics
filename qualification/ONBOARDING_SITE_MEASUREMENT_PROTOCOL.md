# P2 onboarding and investigation site study protocol

Status: **Prepared; not executed.** This protocol does not grant company access or authorize source reads.

## Study question

After internal authorization, measure whether P2 reduces the work required to configure approved read-only sources and reach a defensible first investigation, without reducing source-mapping correctness, evidence coverage, or reviewer control.

## Entry conditions

Do not begin a site session until the source owner and security authority have approved the MCP endpoint, metadata scope, exact read operations, row/time bounds, retention, and permitted audit fields. Use a read-only identity. The synthetic review record, local MCP peer, and local permission label are not site approvals. Stop on denied permission, source/version mismatch, unresolved relationship keys, out-of-scope data, or any need to guess manufacturing semantics. A proposed mapping or query plan must be explicitly reviewed before materialization or execution.

## Matched tasks

Use the same preselected source roles, bounded engineering question, population, time scope, and acceptance oracle for both conditions:

1. **Current-practice baseline:** the site’s documented and approved manual onboarding procedure, selected by the site owner. Do not use the frozen P2 archive as a proxy for this condition; it has no equivalent live onboarding CLI.
2. **P2-assisted:** the authorized descriptor discovery, mapping proposal, engineer review, deterministic preflight, and approved bounded investigation flow.

Use at least two materially distinct approved environments when available. Counterbalance task order across participants or sessions; give both conditions the same source documentation and task briefing. If order or environment cannot be balanced, record that limitation and report results descriptively. Define participant count, tasks, exclusions, and any inferential analysis before observing outcomes; do not choose them after seeing results.

## Record for each task

Use a monotonic timer and the exact P2 revision/package hash. Record total elapsed time and these phases separately: descriptor discovery; source-role and field mapping; relationship/key decisions; authorization review; query-plan review; deterministic preflight; first useful investigation; correction/retry. Also record manual decisions by type, mapping changes, rejected suggestions, incorrect mappings caught before reads, validation failures, retries, approved read count/bounds, and whether the evidence oracle was satisfied.

Have a reviewer who did not configure the task score the final mapping and evidence against the approved task oracle. Score source/relationship identity, event time versus record time, population coverage, exact versus uncertain exposure, route completeness, provenance, counterevidence, and scientific refusal behavior. Record unsupported claims and missing evidence explicitly. A denied or unapproved read must remain unexecuted; any contrary result is a safety failure, not a time-saving success.

Collect only data explicitly approved for the study. Do not place raw manufacturing rows, credentials, or restricted descriptors in general study notes. Use approved opaque identifiers or hashes where permitted. Record interruptions, training, environment differences, and assistance so they are not silently attributed to P2.

## Analysis and reporting

Report per-task paired elapsed times, phase times, decision counts, error/rework counts, task completion, and independent evidence scores. Show all observations and the median/range; report p50/p95 only when the sample supports them. Keep automated elapsed time separate from participant time and count-based proxies. Do not infer company-wide savings from synthetic runs or a small convenience sample.

Estimate economic value only after the site supplies validated labor rates, deployment frequency, support and maintenance effort, and measured baseline/P2 task time. Show the assumptions and uncertainty. A simple gross time estimate is `(baseline measured hours - P2 measured hours) × validated annual onboarding count`; subtract measured P2 setup, review, support, and maintenance effort before presenting any net estimate. No such inputs or ROI are currently verified.

## Required study record

Archive the approved protocol version, participant/task order, approved source-scope record, P2 and tool versions, task-level timings, reviewer scores, deviations, and analysis script under the site’s approved evidence controls. Report synthetic qualification, actual site task-time evidence, source authorization, and economic estimates as separate evidence classes.
