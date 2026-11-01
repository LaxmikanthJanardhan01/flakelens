export interface SystemHealth {
  status: string;
  version: string;
  timestamp: string;
  database: string;
  storage: string;
  environment: string;
}

export interface Project {
  id: string;
  name: string;
  source_archive_path?: string | null;
  created_at: string;
  test_cases_count: number;
}

export interface TestCase {
  id: string;
  project_id: string;
  file_path: string;
  test_name: string;
  node_id: string;
  discovered_at: string;
}

export interface TestRun {
  id: string;
  project_id: string;
  project_name?: string | null;
  run_type?: 'STANDARD' | 'VERIFICATION';
  baseline_run_id?: string | null;
  target_test_case_id?: string | null;
  iteration_count: number;
  completed_iterations?: number;
  shuffle_order: boolean;
  status: 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'TIMED_OUT' | 'CANCELLED';
  total_tests: number;
  consistently_passing_count: number;
  consistently_failing_count: number;
  flaky_tests_count: number;
  insufficient_data_count?: number;
  duration_seconds?: number | null;
  started_at?: string | null;
  completed_at?: string | null;
}

export interface TestIteration {
  id: string;
  test_run_id: string;
  test_case_id: string;
  iteration_number: number;
  status: 'PASSED' | 'FAILED' | 'ERROR' | 'SKIPPED' | 'TIMED_OUT' | 'NOT_EXECUTED';
  duration_ms: number;
  execution_order: number;
  random_order_seed?: number | null;
  stdout?: string | null;
  stderr?: string | null;
  error_message?: string | null;
  traceback?: string | null;
}

export interface FlakinessReport {
  id: string;
  test_run_id: string;
  test_case_id: string;
  node_id?: string | null;
  test_name?: string | null;
  file_path?: string | null;
  outcome_classification: 'CONSISTENTLY_PASSING' | 'CONSISTENTLY_FAILING' | 'FLAKY' | 'INSUFFICIENT_DATA';
  flakiness_score: number;
  total_runs: number;
  pass_count: number;
  fail_count: number;
  flip_count: number;
  root_cause_category?: string | null;
  confidence_score: number;
  rca_summary?: string | null;
  recommendations?: string | null;
  supporting_evidence?: Record<string, any> | null;
}

export interface IterationLogItem {
  iteration_number: number;
  status: string;
  duration_ms: number;
  execution_order: number;
  random_order_seed?: number | null;
  error_message?: string | null;
  traceback?: string | null;
  stdout?: string | null;
  stderr?: string | null;
}

export interface DetailedTestCaseReport extends FlakinessReport {
  iterations: IterationLogItem[];
  pass_rate: number;
  avg_duration_ms: number;
  min_duration_ms: number;
  max_duration_ms: number;
}

export interface DetailedRunReportResponse {
  run_id: string;
  project_id: string;
  project_name: string;
  iteration_count: number;
  status: string;
  total_tests: number;
  consistently_passing_count: number;
  consistently_failing_count: number;
  flaky_tests_count: number;
  insufficient_data_count: number;
  started_at?: string | null;
  completed_at?: string | null;
  reports: DetailedTestCaseReport[];
}

export interface IterationDiffResponse {
  test_case_id: string;
  node_id: string;
  test_name: string;
  passing_iteration?: IterationLogItem | null;
  failing_iteration?: IterationLogItem | null;
  duration_delta_ms?: number | null;
  stdout_diff?: string | null;
  stderr_diff?: string | null;
}

export type TestTransition =
  | 'RECOVERED'
  | 'NEWLY_FAILING'
  | 'NEWLY_FLAKY'
  | 'STILL_FLAKY'
  | 'STILL_FAILING'
  | 'UNCHANGED_PASSING'
  | 'ADDED'
  | 'REMOVED'
  | 'INCONCLUSIVE';

export interface TestComparisonItem {
  test_case_id: string;
  node_id: string;
  test_name: string;
  file_path: string;
  status_a?: string | null;
  status_b?: string | null;
  flakiness_score_a?: number | null;
  flakiness_score_b?: number | null;
  flakiness_score_delta?: number | null;
  pass_rate_a?: number | null;
  pass_rate_b?: number | null;
  avg_duration_ms_a?: number | null;
  avg_duration_ms_b?: number | null;
  duration_delta_ms?: number | null;
  transition: TestTransition;
  rca_category_a?: string | null;
  rca_category_b?: string | null;
}

export interface ComparisonSummaryDelta {
  total_tests_delta: number;
  flaky_count_delta: number;
  passing_count_delta: number;
  failing_count_delta: number;
  recovered_count: number;
  newly_failing_count: number;
  newly_flaky_count: number;
  still_flaky_count: number;
  still_failing_count: number;
  unchanged_passing_count: number;
}

export interface RunComparisonResponse {
  project_id: string;
  project_name: string;
  run_a: TestRun;
  run_b: TestRun;
  summary_delta: ComparisonSummaryDelta;
  test_comparisons: TestComparisonItem[];
}

export interface FixVerificationRequest {
  project_id: string;
  baseline_run_id: string;
  target_test_case_id?: string | null;
  iteration_count?: number;
  shuffle_order?: boolean;
}

export interface TestVerificationDetail {
  test_case_id: string;
  node_id: string;
  test_name: string;
  file_path: string;
  baseline_status: string;
  baseline_flakiness_score: number;
  baseline_pass_count: number;
  baseline_fail_count: number;
  baseline_total_runs: number;
  baseline_rca_category?: string | null;
  verification_status: string;
  verification_flakiness_score: number;
  verification_pass_count: number;
  verification_fail_count: number;
  verification_total_runs: number;
  verdict: 'VERIFIED_FIXED' | 'STILL_FLAKY' | 'STILL_FAILING' | 'INCONCLUSIVE';
  verdict_message: string;
  is_stable: boolean;
}

export interface FixVerificationResponse {
  verification_run: TestRun;
  baseline_run: TestRun;
  overall_verdict: 'VERIFIED_FIXED' | 'STILL_FLAKY' | 'STILL_FAILING' | 'INCONCLUSIVE';
  verdict_summary: string;
  tests: TestVerificationDetail[];
}

