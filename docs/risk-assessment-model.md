# Risk Assessment Model

## Purpose and limits

This document defines the intended confidence and risk-level policy for findings produced from Mnemos-RLI evidence. Confidence describes how complete and timely the observation is; risk level describes the assessed impact of a finding. They are separate dimensions.

These rules are a calibration policy, not a claim that every runtime path currently computes these labels. Until the integration path is verified, reports should preserve the underlying evidence and avoid presenting a proposed label as a validated probability or guarantee.

## Confidence scoring rules

Apply the rules in the order shown. The low-confidence rule is a safety override: incomplete coverage or any unobserved scope prevents a high or medium confidence assignment, even if an event monitor is active.

| Confidence | Conditions | Interpretation |
| --- | --- | --- |
| **high** | `coverage_complete` AND `event_monitor_active` AND `finding_detected_immediately`, provided no low-confidence override applies | Complete declared scope, active event monitoring, and a finding correlated promptly with observed activity. |
| **medium** | `coverage_complete` AND `polling_only` AND `finding_detected_within_interval`, provided no low-confidence override applies | The declared scope is complete, but detection is periodic and may be delayed by the polling interval. |
| **low** | `coverage_incomplete` OR `unobserved_scope` is present | Scope or evidence gaps prevent reliable confidence in the finding's completeness or timing. |

Definitions:

- `coverage_complete`: the scan completed successfully for the declared scope, with no skipped or failed paths that affect the conclusion. This does not mean the entire filesystem is covered.
- `event_monitor_active`: the daemon reports that its filesystem event backend is active. This is activity visibility, not proof that every changed file can be integrity-checked.
- `finding_detected_immediately`: the finding is correlated to the triggering observation during event-driven processing, without waiting for the next periodic scan. Measure and record the actual delay; do not infer immediacy from the backend name alone.
- `polling_only`: no usable event backend is active and periodic scans are the detection mechanism.
- `finding_detected_within_interval`: the finding is detected within the configured polling interval plus measured processing tolerance.
- `unobserved_scope`: any known gap in watched roots, unsupported paths, backend coverage, scan errors, or other declared scope that could conceal relevant activity.

If conditions are missing or contradictory, use **low** confidence until evidence resolves the ambiguity. An active event monitor alone must never elevate confidence when coverage is incomplete.

## Risk-level determination

Apply the highest applicable impact rule first. A risk label must not be inferred from confidence alone; preserve the finding type, asset scope, dependency evidence, and coverage caveats with the result.

| Finding and evidence | Risk level | Rationale |
| --- | --- | --- |
| `hash_mismatch` + **high** confidence + isolated asset | **medium** | Integrity divergence is promptly observed, but available dependency evidence indicates isolated impact. |
| `hash_mismatch` + **high** confidence + critical dependencies | **high** | A well-supported integrity divergence affects an asset with critical dependency relationships and potential broad impact. |
| `hash_mismatch` + **medium** confidence | **low** by default; **info** if impact is unsubstantiated and no corroborating evidence exists | Periodic detection and uncertain timing limit urgency; keep the mismatch visible without overstating impact. |
| `hash_mismatch` + **low** confidence | **info** | Record as an informational lead because incomplete or unobserved scope prevents a stronger conclusion. |

Precedence and safeguards:

1. Incomplete coverage or known unobserved scope forces **low** confidence; it must not be promoted to high confidence solely because an event was observed.
2. Within high-confidence hash mismatches, verified critical dependency evidence takes precedence over the isolated-asset rule.
3. If dependency criticality is unknown, do not assume the asset is isolated or critical. Retain the uncertainty and use a conservative, evidence-backed level.
4. A hash mismatch proves a difference from the selected baseline, not maliciousness or cause. Validate baseline provenance and full-hash quality; sampled fingerprints are not equivalent to full SHA-256.
5. These labels are triage categories, not calibrated probabilities. A **high** risk label must include the evidence that supports impact and confidence.

## Calibration goal

Target a **false-positive rate below 5% for findings labelled `high`** on a representative, reviewed set of real findings.

For calibration, define a false positive as a `high`-labelled finding that a subsequent evidence review determines does not meet the documented high-risk criteria. Track the numerator (reviewed high findings judged false positive) and denominator (all reviewed high findings), record the sample size and review method, and report uncertainty when the sample is small. Do not claim the target is achieved until sufficient reviewed data supports it.

The target concerns the high risk level, not the confidence label. Keep these metrics separate.

## Next validation step

After documenting the model:

1. Run the existing integration paths for file-change detection, integrity comparison, monitoring status, and finding persistence; do not treat this document itself as implementation or test evidence.
2. Collect real findings with their scope completeness, active backend, detection delay, hash quality, dependency evidence, assigned confidence, and assigned risk level.
3. Review false positives and false negatives, especially high-risk findings; adjust thresholds only from recorded evidence and document the rationale for each adjustment.
4. Verify that API and CLI outputs expose the same labels and supporting evidence. Until that is confirmed, describe the rules as the intended model and avoid claiming the calibration target has been met.
