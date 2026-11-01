import json
import logging
import math
import re
from typing import Dict, List, Optional, Tuple, Any
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.db.models import TestCase, TestRun, TestIteration, FlakinessReport
from backend.app.core.detector import ActiveRunAnalysisError

logger = logging.getLogger("flakelens.core.rca")


class RCACategory:
    ORDER_DEPENDENCY = "ORDER_DEPENDENCY"
    SHARED_STATE_POLLUTION = "SHARED_STATE_POLLUTION"
    TIMING_OR_RACE_CONDITION = "TIMING_OR_RACE_CONDITION"
    RESOURCE_EXHAUSTION = "RESOURCE_EXHAUSTION"
    ENVIRONMENT_DEPENDENCY = "ENVIRONMENT_DEPENDENCY"
    EXTERNAL_DEPENDENCY = "EXTERNAL_DEPENDENCY"
    ASSERTION_OR_LOGIC_FAILURE = "ASSERTION_OR_LOGIC_FAILURE"
    UNKNOWN = "UNKNOWN"


class RCAEngine:
    """
    Deterministic, evidence-based Root Cause Analysis (RCA) Engine.
    Analyzes persisted execution telemetry from Milestone 3 and classifications from Milestone 4
    to diagnose root causes, compute evidence-confidence scores, generate 4-part summaries,
    and provide actionable remediation recommendations.

    Engineering Guarantees:
    1. Caller transaction ownership: Uses nested savepoints (`db.begin_nested()`) and flushes
       without committing caller-owned outer transactions.
    2. Minimum sample requirements: Requires >= 2 passes and >= 2 failures before evaluating
       relative execution order permutation correlation.
    3. Permutation correlation vs. bisection: Observes order correlation under randomized shuffling;
       never claims active binary bisection or definitive causation.
    4. Corroborated resource exhaustion: A container TIMED_OUT status alone never implies resource exhaustion.
    5. Duration spread filter: Requires both CV > 0.40 and absolute duration spread >= 200ms.
    6. Boundary-aware regex patterns: Replaces brittle substring matching to prevent false positives.
    7. Contradiction penalty: Competing signals reduce evidence confidence proportionally.
    """

    STATE_POLLUTION_PATTERNS = [
        re.compile(r"\bstate\s+pollution\b", re.I),
        re.compile(r"\bdirty\s+state\b", re.I),
        re.compile(r"\bshared\s+state\b", re.I),
        re.compile(r"\b(?:uncleaned|residual|leaked)\s+state\b", re.I),
        re.compile(r"\btable\s+already\s+exists\b", re.I),
        re.compile(r"\bduplicate\s+key\b", re.I),
        re.compile(r"\bdatabase\s+is\s+locked\b", re.I),
        re.compile(r"\bsingleton.*already\s+(?:initialized|exists)\b", re.I),
        re.compile(r"\bglobal\s+variable.*pollut\w*\b", re.I),
        re.compile(r"\bcache.*residual\b", re.I),
        re.compile(r"\buncleaned\s+residual\b", re.I),
        re.compile(r"\bnot\s+clean\b", re.I),
    ]

    TIMING_PATTERNS = [
        re.compile(r"\brace\s+condition\b", re.I),
        re.compile(r"\basyncio\.exceptions\.timeouterror\b", re.I),
        re.compile(r"\bconcurrent\.futures\.timeouterror\b", re.I),
        re.compile(r"\btimed\s+out\s+waiting\s+for\b", re.I),
        re.compile(r"\bevent\s+loop\s+is\s+closed\b", re.I),
        re.compile(r"\bevent\s+loop\b", re.I),
        re.compile(r"\bdeadlock\s+detected\b", re.I),
        re.compile(r"\bthread\s+deadlock\b", re.I),
        re.compile(r"\block\s+acquisition\s+timeout\b", re.I),
        re.compile(r"\basyncio\.wait_for\b", re.I),
    ]

    RESOURCE_PATTERNS = [
        re.compile(r"\bmemoryerror\b", re.I),
        re.compile(r"\bout\s+of\s+memory\b", re.I),
        re.compile(r"\btoo\s+many\s+open\s+files\b", re.I),
        re.compile(r"\boserror:\s*\[errno\s*24\]", re.I),
        re.compile(r"\bdisk\s+full\b", re.I),
        re.compile(r"\bno\s+space\s+left\s+on\s+device\b", re.I),
        re.compile(r"\boserror:\s*\[errno\s*28\]", re.I),
        re.compile(r"\bpids\s+limit\s+exceeded\b", re.I),
        re.compile(r"\boom-killer\b", re.I),
    ]

    ENVIRONMENT_PATTERNS = [
        re.compile(r"\bfilenotfounderror\b", re.I),
        re.compile(r"\bmodulenotfounderror\b", re.I),
        re.compile(r"\bimporterror\b", re.I),
        re.compile(r"\bpermissionerror\b", re.I),
        re.compile(r"\bno\s+such\s+file\s+or\s+directory\b", re.I),
        re.compile(r"\bpath\s+does\s+not\s+exist\b", re.I),
        re.compile(r"\bmissing\s+environment\s+variable\b", re.I),
        re.compile(r"\bos\.environ\[", re.I),
        re.compile(r"\blocale\.error\b", re.I),
        re.compile(r"\bunknown\s+timezone\b", re.I),
    ]

    EXTERNAL_DEPENDENCY_PATTERNS = [
        re.compile(r"\bconnectionrefusederror\b", re.I),
        re.compile(r"\bsocket\.gaierror\b", re.I),
        re.compile(r"\bhttpx\.connecterror\b", re.I),
        re.compile(r"\brequests\.exceptions\.connectionerror\b", re.I),
        re.compile(r"\bconnectionreseterror\b", re.I),
        re.compile(r"\burllib\.error\.urlerror\b", re.I),
        re.compile(r"\bfailed\s+to\s+establish\s+a\s+new\s+connection\b", re.I),
        re.compile(r"\bnetwork\s+is\s+unreachable\b", re.I),
        re.compile(r"\bgetaddrinfo\s+failed\b", re.I),
    ]

    def analyze_test_run_rca(
        self,
        test_run_id: str,
        db: Session,
        allow_active: bool = False,
    ) -> List[FlakinessReport]:
        """
        Executes root cause analysis for all FlakinessReport records of a test run.

        Transaction Safety:
        - Uses a nested savepoint (`db.begin_nested()`).
        - Flushes changes without committing the caller's outer transaction.
        - On exception, savepoint rolls back RCA changes cleanly and re-raises.
        """
        test_run = db.query(TestRun).filter(TestRun.id == test_run_id).first()
        if not test_run:
            raise ValueError(f"TestRun with ID '{test_run_id}' does not exist.")

        if not allow_active and test_run.status == "RUNNING":
            raise ActiveRunAnalysisError(
                f"Cannot perform root cause analysis on run '{test_run_id}' while execution is actively running."
            )

        # Query project-scoped test cases
        project_test_cases = (
            db.query(TestCase)
            .filter(TestCase.project_id == test_run.project_id)
            .all()
        )
        tc_by_id = {tc.id: tc for tc in project_test_cases}

        # Query existing reports for this run
        reports = (
            db.query(FlakinessReport)
            .filter(FlakinessReport.test_run_id == test_run_id)
            .all()
        )
        report_by_tc = {r.test_case_id: r for r in reports}

        # Query all iterations for this run
        all_iterations = (
            db.query(TestIteration)
            .filter(TestIteration.test_run_id == test_run_id)
            .order_by(TestIteration.iteration_number.asc(), TestIteration.execution_order.asc())
            .all()
        )

        # Build suite execution map: iteration_number -> list of iterations sorted by execution_order
        suite_map_by_iter: Dict[int, List[TestIteration]] = {}
        # Map iterations by test_case_id: tc_id -> list of iterations
        iters_by_tc: Dict[str, List[TestIteration]] = {}
        for it in all_iterations:
            suite_map_by_iter.setdefault(it.iteration_number, []).append(it)
            iters_by_tc.setdefault(it.test_case_id, []).append(it)

        updated_reports: List[FlakinessReport] = []

        # Execute RCA within a transaction savepoint to isolate RCA operations
        try:
            with db.begin_nested():
                for tc_id, report in report_by_tc.items():
                    if tc_id not in tc_by_id:
                        continue

                    tc = tc_by_id[tc_id]
                    tc_iters = iters_by_tc.get(tc_id, [])

                    category, confidence, summary, recs, evidence = self._evaluate_test_case_rca(
                        report=report,
                        tc=tc,
                        tc_iters=tc_iters,
                        suite_map_by_iter=suite_map_by_iter,
                        tc_by_id=tc_by_id,
                        test_run=test_run,
                    )

                    report.root_cause_category = category
                    report.confidence_score = confidence
                    report.rca_summary = summary
                    report.recommendations = recs
                    report.supporting_evidence = json.dumps(evidence) if evidence else None

                    db.add(report)
                    updated_reports.append(report)

                # Flush updates to stage them in the savepoint without committing outer transaction
                db.flush()
        except Exception:
            # Savepoint rollback is automatically performed by begin_nested() context manager
            logger.exception(f"Error during RCA computation for run '{test_run_id}'; rolled back savepoint.")
            raise

        for r in updated_reports:
            db.refresh(r)

        return updated_reports

    def _evaluate_test_case_rca(
        self,
        report: FlakinessReport,
        tc: TestCase,
        tc_iters: List[TestIteration],
        suite_map_by_iter: Dict[int, List[TestIteration]],
        tc_by_id: Dict[str, TestCase],
        test_run: Optional[TestRun] = None,
    ) -> Tuple[Optional[str], float, str, str, Dict[str, Any]]:
        """
        Evaluates telemetry and computes RCA diagnosis for a single test case report.
        Returns: (category, confidence_score, rca_summary, recommendations, supporting_evidence)
        """
        # Case A: Stable passing test
        if report.outcome_classification == "CONSISTENTLY_PASSING":
            return (
                None,
                0.0,  # Neutral numeric representation for tests with no failure
                f"1. What was observed: Test '{tc.test_name}' passed consistently across all {report.total_runs} valid executions.\n"
                f"2. Telemetry evidence: Zero failures, timeouts, or state flips recorded ({report.pass_count}P / 0F).\n"
                f"3. Category selection: No failure detected; test exhibits stable deterministic execution.\n"
                f"4. Uncertainties: None.",
                "Test is stable and passing. No remediation or investigation required.",
                {
                    "observed_pass_count": report.pass_count,
                    "observed_fail_count": 0,
                    "total_valid_runs": report.total_runs,
                    "flakiness_score": 0.0,
                    "contradiction_penalty": 0.0,
                },
            )

        # Case B: Insufficient telemetry (fewer than 2 valid runs)
        if report.outcome_classification == "INSUFFICIENT_DATA" and report.total_runs < 2:
            return (
                RCACategory.UNKNOWN,
                0.10,
                f"1. What was observed: Insufficient execution data for test '{tc.test_name}' ({report.total_runs} valid run(s)).\n"
                f"2. Telemetry evidence: At least 5 valid iterations required; {report.total_runs} observed.\n"
                f"3. Category selection: UNKNOWN due to lack of statistical telemetry.\n"
                f"4. Uncertainties: True failure distribution and error mechanisms cannot be established without repeated executions.",
                "Execute the test suite with a minimum of 5 iterations to gather sufficient empirical telemetry.",
                {
                    "observed_pass_count": report.pass_count,
                    "observed_fail_count": report.fail_count,
                    "total_valid_runs": report.total_runs,
                    "contradiction_penalty": 0.0,
                    "uncertainty_notes": ["Fewer than 2 valid executions recorded."],
                },
            )

        # Case C: Flaky, Consistently Failing, or Insufficient Data with >=2 runs
        # 1. Telemetry duration statistics
        valid_iters = [it for it in tc_iters if it.status in ("PASSED", "FAILED", "TIMED_OUT")]
        durations = [it.duration_ms for it in valid_iters if it.duration_ms > 0]
        mean_dur = sum(durations) / len(durations) if durations else 0.0
        variance = (
            sum((d - mean_dur) ** 2 for d in durations) / len(durations)
            if len(durations) > 1
            else 0.0
        )
        std_dur = math.sqrt(variance)
        cv_dur = (std_dur / mean_dur) if mean_dur > 0 else 0.0
        dur_spread = (max(durations) - min(durations)) if durations else 0.0

        failing_iters = [it for it in valid_iters if it.status in ("FAILED", "TIMED_OUT")]
        passing_iters = [it for it in valid_iters if it.status == "PASSED"]

        # Aggregate text logs from failures
        fail_msgs = [it.error_message for it in failing_iters if it.error_message]
        fail_tbs = [it.traceback for it in failing_iters if it.traceback]
        combined_fail_text = " ".join(fail_msgs + fail_tbs)

        # 2. Category Evidence Accumulator
        evidence_scores: Dict[str, float] = {
            RCACategory.ORDER_DEPENDENCY: 0.0,
            RCACategory.SHARED_STATE_POLLUTION: 0.0,
            RCACategory.TIMING_OR_RACE_CONDITION: 0.0,
            RCACategory.RESOURCE_EXHAUSTION: 0.0,
            RCACategory.ENVIRONMENT_DEPENDENCY: 0.0,
            RCACategory.EXTERNAL_DEPENDENCY: 0.0,
            RCACategory.ASSERTION_OR_LOGIC_FAILURE: 0.0,
        }

        matched_signatures: List[str] = []
        suspect_preceding_tests: List[Dict[str, Any]] = []
        uncertainty_notes: List[str] = []

        # --- A. Execution Order Permutation Correlation Analysis ---
        is_shuffled = getattr(test_run, "shuffle_order", True) if test_run else True
        has_min_order_samples = len(failing_iters) >= 2 and len(passing_iters) >= 2

        if failing_iters and passing_iters:
            if not is_shuffled:
                uncertainty_notes.append(
                    "Test order shuffling was disabled (shuffle_order=False); test order permutation correlation cannot infer order dependency from identical sequence."
                )
            elif not has_min_order_samples:
                uncertainty_notes.append(
                    f"Insufficient outcome distribution ({len(passing_iters)}P / {len(failing_iters)}F, minimum 2P and 2F required) to establish relative order correlation."
                )
            else:
                fail_iter_nums = {it.iteration_number for it in failing_iters}
                pass_iter_nums = {it.iteration_number for it in passing_iters}

                preceding_in_fail: Dict[str, int] = {}
                preceding_in_pass: Dict[str, int] = {}

                tc_order_by_iter: Dict[int, int] = {
                    it.iteration_number: it.execution_order for it in valid_iters if it.execution_order is not None
                }

                # Verify if test positions actually varied across iterations
                distinct_orders = len(set(tc_order_by_iter.values()))
                if distinct_orders <= 1 and len(tc_order_by_iter) > 1:
                    uncertainty_notes.append(
                        "Insufficient execution order variation across iterations to establish relative order correlation."
                    )
                else:
                    for iter_num, iter_tests in suite_map_by_iter.items():
                        if iter_num not in tc_order_by_iter:
                            continue
                        t_order = tc_order_by_iter[iter_num]

                        for other_it in iter_tests:
                            if other_it.test_case_id == tc.id or other_it.execution_order is None:
                                continue
                            if other_it.execution_order < t_order:
                                other_id = other_it.test_case_id
                                if iter_num in fail_iter_nums:
                                    preceding_in_fail[other_id] = preceding_in_fail.get(other_id, 0) + 1
                                elif iter_num in pass_iter_nums:
                                    preceding_in_pass[other_id] = preceding_in_pass.get(other_id, 0) + 1

                    # Identify suspected preceding tests (permutation correlation candidates)
                    for other_id, fail_prec_count in preceding_in_fail.items():
                        pass_prec_count = preceding_in_pass.get(other_id, 0)
                        fail_ratio = fail_prec_count / len(failing_iters)
                        pass_ratio = pass_prec_count / len(passing_iters) if passing_iters else 0.0

                        other_tc = tc_by_id.get(other_id)
                        other_node_id = other_tc.node_id if other_tc else other_id

                        # Strong correlation: precedes in 100% of failures, 0% of passes (heuristic candidate)
                        if fail_ratio == 1.0 and pass_ratio == 0.0:
                            suspect_preceding_tests.append({
                                "test_case_id": other_id,
                                "node_id": other_node_id,
                                "preceded_in_failures": fail_prec_count,
                                "preceded_in_passes": pass_prec_count,
                                "correlation_score": 1.0,
                                "suspect_status": "heuristic_candidate",
                            })
                            evidence_scores[RCACategory.ORDER_DEPENDENCY] += 0.75
                        elif fail_ratio >= 0.75 and pass_ratio <= 0.25:
                            suspect_preceding_tests.append({
                                "test_case_id": other_id,
                                "node_id": other_node_id,
                                "preceded_in_failures": fail_prec_count,
                                "preceded_in_passes": pass_prec_count,
                                "correlation_score": round(fail_ratio - pass_ratio, 2),
                                "suspect_status": "heuristic_candidate",
                            })
                            evidence_scores[RCACategory.ORDER_DEPENDENCY] += 0.50

                    # Execution order position difference
                    avg_fail_order = sum(tc_order_by_iter[it.iteration_number] for it in failing_iters if it.iteration_number in tc_order_by_iter) / len(failing_iters)
                    avg_pass_order = sum(tc_order_by_iter[it.iteration_number] for it in passing_iters if it.iteration_number in tc_order_by_iter) / len(passing_iters)
                    if avg_fail_order >= avg_pass_order + 1.0:
                        evidence_scores[RCACategory.ORDER_DEPENDENCY] += 0.20

        # State pollution regex matching
        pollution_hits = [
            p.pattern for p in self.STATE_POLLUTION_PATTERNS if p.search(combined_fail_text)
        ]
        if pollution_hits:
            evidence_scores[RCACategory.SHARED_STATE_POLLUTION] += 0.70
            matched_signatures.extend([f"state_pollution: '{p}'" for p in pollution_hits[:3]])

        # If order correlation candidates exist AND state pollution keywords exist, boost SHARED_STATE_POLLUTION
        if suspect_preceding_tests and pollution_hits:
            evidence_scores[RCACategory.SHARED_STATE_POLLUTION] += 0.35

        # --- B. Timing / Race Condition Analysis ---
        timing_hits = [
            p.pattern for p in self.TIMING_PATTERNS if p.search(combined_fail_text)
        ]
        if timing_hits:
            evidence_scores[RCACategory.TIMING_OR_RACE_CONDITION] += 0.55
            matched_signatures.extend([f"timing_signature: '{p}'" for p in timing_hits[:3]])

        # Duration variance heuristic requires BOTH CV > 0.40 AND meaningful absolute duration spread >= 200ms
        if cv_dur > 0.40 and dur_spread >= 200.0:
            evidence_scores[RCACategory.TIMING_OR_RACE_CONDITION] += 0.25
            matched_signatures.append(f"duration_variance: CV={cv_dur:.2f}, spread={dur_spread:.0f}ms")

        if report.flip_count >= max(2, report.total_runs // 2):
            evidence_scores[RCACategory.TIMING_OR_RACE_CONDITION] += 0.15

        # --- C. Resource Exhaustion Analysis ---
        resource_hits = [
            p.pattern for p in self.RESOURCE_PATTERNS if p.search(combined_fail_text)
        ]
        if resource_hits:
            evidence_scores[RCACategory.RESOURCE_EXHAUSTION] += 0.80
            matched_signatures.extend([f"resource_signature: '{p}'" for p in resource_hits[:3]])

        # Container timeout status handling (TIMED_OUT alone must NOT establish RESOURCE_EXHAUSTION)
        timeout_iters = [it for it in failing_iters if it.status == "TIMED_OUT"]
        if timeout_iters:
            if resource_hits:
                # Corroborated: hit timeout AND has resource exhaustion signature
                evidence_scores[RCACategory.RESOURCE_EXHAUSTION] += 0.40
                matched_signatures.append(f"timeout_with_resource_exhaustion: {len(timeout_iters)} run(s)")
            elif timing_hits:
                evidence_scores[RCACategory.TIMING_OR_RACE_CONDITION] += 0.30
                matched_signatures.append(f"timeout_with_timing_signature: {len(timeout_iters)} run(s)")
            elif any(p.search(combined_fail_text) for p in self.EXTERNAL_DEPENDENCY_PATTERNS):
                evidence_scores[RCACategory.EXTERNAL_DEPENDENCY] += 0.30
                matched_signatures.append(f"timeout_with_network_signature: {len(timeout_iters)} run(s)")
            else:
                matched_signatures.append(f"timeout_unattributed: {len(timeout_iters)} run(s) timed out")
                uncertainty_notes.append(
                    f"{len(timeout_iters)} execution(s) timed out without explicit memory or descriptor exhaustion signatures; symptom remains ambiguous."
                )

        # --- D. Environment Dependency Analysis ---
        env_hits = [
            p.pattern for p in self.ENVIRONMENT_PATTERNS if p.search(combined_fail_text)
        ]
        if env_hits:
            evidence_scores[RCACategory.ENVIRONMENT_DEPENDENCY] += 0.75
            matched_signatures.extend([f"environment_signature: '{p}'" for p in env_hits[:3]])

        # --- E. External Dependency Analysis ---
        ext_hits = [
            p.pattern for p in self.EXTERNAL_DEPENDENCY_PATTERNS if p.search(combined_fail_text)
        ]
        if ext_hits:
            evidence_scores[RCACategory.EXTERNAL_DEPENDENCY] += 0.85
            matched_signatures.extend([f"network_dependency: '{p}'" for p in ext_hits[:3]])

        # --- F. Assertion / Logic Failure ---
        if report.outcome_classification == "CONSISTENTLY_FAILING":
            evidence_scores[RCACategory.ASSERTION_OR_LOGIC_FAILURE] += 0.85
            if fail_msgs:
                matched_signatures.append(f"deterministic_failure: '{fail_msgs[0][:60]}'")
        elif report.outcome_classification == "FLAKY":
            # For intermittent tests, only consider assertion failure if no other signature matched
            if not timing_hits and not pollution_hits and not suspect_preceding_tests and not resource_hits and not env_hits and not ext_hits:
                if any("assertionerror" in text.lower() for text in fail_msgs + fail_tbs):
                    evidence_scores[RCACategory.ASSERTION_OR_LOGIC_FAILURE] += 0.30

        # --- 3. Determine Highest Category & Evidence Confidence with Contradiction Penalty ---
        sample_size_factor = min(1.0, report.total_runs / 5.0)
        for cat in evidence_scores:
            evidence_scores[cat] *= sample_size_factor

        sorted_categories = sorted(evidence_scores.items(), key=lambda kv: kv[1], reverse=True)
        top_category, top_score = sorted_categories[0]
        second_category, second_score = sorted_categories[1]

        if report.total_runs < 5:
            uncertainty_notes.append(f"Sample size ({report.total_runs} runs) is below the threshold of 5.")

        # Contradiction penalty: if strongest competing category has significant evidence (>= 0.30)
        contradiction_penalty = 0.0
        if top_score > 0 and second_score >= 0.30:
            contradiction_penalty = min(0.35, second_score * 0.40)
            top_score = max(0.0, top_score - contradiction_penalty)
            uncertainty_notes.append(
                f"Conflicting signals observed: secondary evidence for {second_category} (score {round(second_score, 2)}) "
                f"reduced evidence confidence by {round(contradiction_penalty, 2)}."
            )

        if top_score < 0.35:
            final_category = RCACategory.UNKNOWN
            final_confidence = min(0.30, round(top_score, 2))
            uncertainty_notes.append("Telemetry evidence does not strongly match any single root cause category.")
        else:
            final_category = top_category
            # Bounded between 0.35 and 0.95 (heuristic evidence score, never 1.0)
            final_confidence = min(0.95, max(0.35, round(top_score, 2)))

        # Build 4-part structured explanation
        summary = self._generate_rca_summary(
            category=final_category,
            confidence=final_confidence,
            report=report,
            tc=tc,
            matched_signatures=matched_signatures,
            suspects=suspect_preceding_tests,
            uncertainty_notes=uncertainty_notes,
            cv_dur=cv_dur,
            dur_spread=dur_spread,
        )

        recommendations = self._generate_recommendations(
            category=final_category,
            suspects=suspect_preceding_tests,
        )

        supporting_evidence = {
            "observed_pass_count": report.pass_count,
            "observed_fail_count": report.fail_count,
            "total_valid_runs": report.total_runs,
            "flakiness_score": report.flakiness_score,
            "flip_count": report.flip_count,
            "duration_stats": {
                "mean_ms": round(mean_dur, 2),
                "std_dev_ms": round(std_dur, 2),
                "coefficient_of_variation": round(cv_dur, 2),
                "spread_ms": round(dur_spread, 2),
            },
            "suspect_preceding_tests": suspect_preceding_tests,
            "matched_signatures": matched_signatures,
            "evidence_scores": {k: round(v, 2) for k, v in evidence_scores.items() if v > 0},
            "contradiction_penalty": round(contradiction_penalty, 2),
            "uncertainty_notes": uncertainty_notes,
        }

        return final_category, final_confidence, summary, recommendations, supporting_evidence

    def _generate_rca_summary(
        self,
        category: str,
        confidence: float,
        report: FlakinessReport,
        tc: TestCase,
        matched_signatures: List[str],
        suspects: List[Dict[str, Any]],
        uncertainty_notes: List[str],
        cv_dur: float,
        dur_spread: float,
    ) -> str:
        """Constructs human-readable 4-part root cause summary answering all mandatory questions."""
        # 1. What was observed?
        if report.outcome_classification == "CONSISTENTLY_FAILING":
            observed = f"Test '{tc.test_name}' failed consistently in 100% of iterations ({report.fail_count} failures across {report.total_runs} valid executions)."
        else:
            observed = f"Test '{tc.test_name}' exhibited intermittent outcomes ({report.pass_count}P / {report.fail_count}F, flakiness score F={report.flakiness_score:.4f}, flip count κ={report.flip_count})."

        # 2. Supporting telemetry
        evidence_lines = []
        if suspects:
            s_names = [f"'{s['node_id']}' (preceded {s['preceded_in_failures']}/{report.fail_count} failures)" for s in suspects[:2]]
            evidence_lines.append(f"Execution order permutation correlation identified suspected preceding test(s) {', '.join(s_names)}.")
        if matched_signatures:
            evidence_lines.append(f"Matched telemetry signatures: {', '.join(matched_signatures[:3])}.")
        if cv_dur > 0.40 and dur_spread >= 200.0:
            evidence_lines.append(f"Execution duration showed high volatility (CV={cv_dur:.2f}, spread={dur_spread:.0f}ms).")
        if not evidence_lines:
            evidence_lines.append("No definitive error signature or execution order correlation was observed.")
        telemetry = " ".join(evidence_lines)

        # 3. Category selection reasoning
        reasoning_map = {
            RCACategory.ORDER_DEPENDENCY: "Classified as ORDER_DEPENDENCY because failures systematically correlate with preceding test execution order under randomized shuffling.",
            RCACategory.SHARED_STATE_POLLUTION: "Classified as SHARED_STATE_POLLUTION due to explicit state pollution error signatures combined with preceding test mutator activity.",
            RCACategory.TIMING_OR_RACE_CONDITION: "Classified as TIMING_OR_RACE_CONDITION because telemetry indicates asynchronous worker delays, sleep-wait vulnerabilities, or high timing variance.",
            RCACategory.RESOURCE_EXHAUSTION: "Classified as RESOURCE_EXHAUSTION because execution encountered memory exhaustion, descriptor limits, or corroborated system resource exhaustion.",
            RCACategory.ENVIRONMENT_DEPENDENCY: "Classified as ENVIRONMENT_DEPENDENCY due to missing filesystem paths, modules, or unconfigured environment variables.",
            RCACategory.EXTERNAL_DEPENDENCY: "Classified as EXTERNAL_DEPENDENCY because unmocked external network/socket connection attempts failed in the isolated sandbox.",
            RCACategory.ASSERTION_OR_LOGIC_FAILURE: "Classified as ASSERTION_OR_LOGIC_FAILURE because the failure is deterministic across all iterations and represents a code regression or broken assertion.",
            RCACategory.UNKNOWN: "Classified as UNKNOWN because telemetry evidence was ambiguous, conflicting, or insufficient to isolate a root cause.",
        }
        selection = reasoning_map.get(category, "Category selected based on evidence weighting.")

        # 4. What remains uncertain?
        uncertainties = " ".join(uncertainty_notes) if uncertainty_notes else "Root cause is strongly supported by consistent multi-iteration evidence."

        return (
            f"1. What was observed: {observed}\n"
            f"2. Telemetry evidence: {telemetry}\n"
            f"3. Category selection: {selection}\n"
            f"4. Uncertainties: {uncertainties}"
        )

    def _generate_recommendations(
        self,
        category: str,
        suspects: List[Dict[str, Any]],
    ) -> str:
        """Constructs category-specific, actionable remediation recommendations."""
        if category == RCACategory.ORDER_DEPENDENCY:
            if suspects:
                s_name = suspects[0]["node_id"]
                return (
                    f"1. Isolate test fixtures: investigate suspected preceding test '{s_name}', which systematically preceded this test in failing runs under randomized shuffling.\n"
                    f"2. Ensure '{s_name}' cleans up shared state in a pytest fixture teardown (`yield`).\n"
                    f"3. Run both tests in isolation (`pytest {s_name} <this_test>`) to reproduce the order dependency deterministically."
                )
            return (
                "1. Decouple test from execution order assumptions.\n"
                "2. Ensure all required test prerequisites are initialized within local pytest fixtures.\n"
                "3. Use `pytest --random-order` locally to verify that test pass/fail does not depend on order."
            )
        elif category == RCACategory.SHARED_STATE_POLLUTION:
            return (
                "1. Reset shared mutable state: replace global variables or singleton caches with function-scoped or class-scoped fixtures.\n"
                "2. Implement fixture teardown with `yield` to guarantee state cleanup even when tests fail.\n"
                "3. Ensure database transactions or in-memory caches roll back after each test."
            )
        elif category == RCACategory.TIMING_OR_RACE_CONDITION:
            return (
                "1. Avoid fixed `time.sleep()` calls in asynchronous test code.\n"
                "2. Replace fixed waits with explicit condition polling (e.g. `wait_until`, `pytest.approx`, or `asyncio.wait_for`).\n"
                "3. Inspect thread join timeouts and thread synchronization primitives (Locks, Events, Semaphores)."
            )
        elif category == RCACategory.RESOURCE_EXHAUSTION:
            return (
                "1. Investigate container timeout and resource consumption: check for deadlocks, infinite loops, or unclosed file handles.\n"
                "2. Ensure temporary files and subprocesses are explicitly terminated and cleaned up in fixture teardown.\n"
                "3. If legitimate workload requires longer execution, adjust `DOCKER_ITERATION_TIMEOUT` in settings."
            )
        elif category == RCACategory.ENVIRONMENT_DEPENDENCY:
            return (
                "1. Eliminate hardcoded filesystem paths; use pytest's `tmp_path` fixture for temporary file operations.\n"
                "2. Mock environment variables using `monkeypatch.setenv()` rather than relying on host system environment.\n"
                "3. Verify all required package dependencies are declared in `requirements.txt`."
            )
        elif category == RCACategory.EXTERNAL_DEPENDENCY:
            return (
                "1. Mock external HTTP and socket endpoints: the FLAKELENS execution container runs with `--network none`.\n"
                "2. Use mocking libraries such as `responses`, `requests-mock`, `aioresponses`, or `unittest.mock`.\n"
                "3. Never perform unmocked live network requests in unit or integration test suites."
            )
        elif category == RCACategory.ASSERTION_OR_LOGIC_FAILURE:
            return (
                "1. This is a deterministic regression or assertion bug, not a flaky timing issue.\n"
                "2. Inspect the failed assertion message and compare actual vs. expected values in application logic.\n"
                "3. Fix the underlying bug or update the assertion if application behavior was intentionally changed."
            )
        else:
            return (
                "1. Telemetry evidence is insufficient or inconclusive to isolate a definitive root cause.\n"
                "2. Re-run analysis with higher iteration count (e.g. 10+ iterations) and order shuffling enabled.\n"
                "3. Inspect stdout/stderr logs in the active run inspector for subtle intermittent errors."
            )
