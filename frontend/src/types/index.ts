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
  iteration_count: number;
  completed_iterations?: number;
  shuffle_order: boolean;
  status: 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'TIMED_OUT' | 'CANCELLED';
  total_tests: number;
  consistently_passing_count: number;
  consistently_failing_count: number;
  flaky_tests_count: number;
  insufficient_data_count?: number;
  started_at?: string | null;
  completed_at?: string | null;
}

export interface TestIteration {
  id: string;
  test_run_id: string;
  test_case_id: string;
  iteration_number: number;
  status: 'PASSED' | 'FAILED' | 'ERROR' | 'SKIPPED';
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

