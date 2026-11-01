import React, { useEffect, useState } from 'react';
import {
  FileBarChart2,
  Filter,
  AlertTriangle,
  XCircle,
  CheckCircle2,
  HelpCircle,
  RefreshCw,
  Activity,
  GitBranch,
  Clock,
  Cpu,
  Globe,
  Terminal,
  Wrench,
  Bug,
  Info,
  ShieldCheck,
  X,
  Play,
  Copy,
  Check,
} from 'lucide-react';
import { EmptyState } from '../components/EmptyState';
import { runsApi, reportsApi, verificationApi } from '../services/api';
import { TestRun, DetailedTestCaseReport, IterationLogItem } from '../types';

interface ReportViewProps {
  initialRunId?: string;
  onNavigateToNew: () => void;
  onNavigateToActiveRun?: (runId: string) => void;
}

export const ReportView: React.FC<ReportViewProps> = ({
  initialRunId,
  onNavigateToNew,
  onNavigateToActiveRun,
}) => {
  const [runs, setRuns] = useState<TestRun[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string>(initialRunId || '');
  const [reports, setReports] = useState<DetailedTestCaseReport[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [analyzing, setAnalyzing] = useState<boolean>(false);
  const [filter, setFilter] = useState<
    'ALL' | 'FLAKY' | 'FAILING' | 'PASSING' | 'INSUFFICIENT_DATA'
  >('ALL');

  // Modal states
  const [selectedIteration, setSelectedIteration] = useState<{
    test: DetailedTestCaseReport;
    iteration: IterationLogItem;
  } | null>(null);

  const [verifyModalTest, setVerifyModalTest] = useState<DetailedTestCaseReport | null>(null);
  const [verifyIterations, setVerifyIterations] = useState<number>(10);
  const [verifyShuffle, setVerifyShuffle] = useState<boolean>(true);
  const [verifying, setVerifying] = useState<boolean>(false);
  const [copiedLog, setCopiedLog] = useState<boolean>(false);

  useEffect(() => {
    const fetchRuns = async () => {
      try {
        setLoading(true);
        const runList = await runsApi.list();
        setRuns(runList);
        if (runList.length > 0) {
          if (initialRunId && runList.some((r) => r.id === initialRunId)) {
            setSelectedRunId(initialRunId);
          } else {
            setSelectedRunId(runList[0].id);
          }
        }
      } catch {
        setRuns([]);
      } finally {
        setLoading(false);
      }
    };
    fetchRuns();
  }, [initialRunId]);

  const fetchReports = async (runId: string) => {
    try {
      setLoading(true);
      const data = await reportsApi.getDetailed(runId);
      setReports(data.reports || []);
    } catch {
      // Fallback to basic reports if detailed endpoint is unavailable
      try {
        const basicData = await reportsApi.getByRun(runId);
        setReports(
          basicData.map((b) => ({
            ...b,
            iterations: [],
            pass_rate: b.total_runs > 0 ? b.pass_count / b.total_runs : 0,
            avg_duration_ms: 0,
            min_duration_ms: 0,
            max_duration_ms: 0,
          }))
        );
      } catch {
        setReports([]);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!selectedRunId) {
      setReports([]);
      return;
    }
    fetchReports(selectedRunId);
  }, [selectedRunId]);

  const handleAnalyze = async () => {
    if (!selectedRunId) return;
    try {
      setAnalyzing(true);
      await reportsApi.analyze(selectedRunId);
      await fetchReports(selectedRunId);
      const runList = await runsApi.list();
      setRuns(runList);
    } catch (err) {
      console.error('Failed to trigger analysis:', err);
    } finally {
      setAnalyzing(false);
    }
  };

  const handleLaunchVerification = async () => {
    if (!verifyModalTest || !selectedRun) return;
    try {
      setVerifying(true);
      const newRun = await verificationApi.start({
        project_id: selectedRun.project_id,
        baseline_run_id: selectedRun.id,
        target_test_case_id: verifyModalTest.test_case_id,
        iteration_count: verifyIterations,
        shuffle_order: verifyShuffle,
      });
      setVerifyModalTest(null);
      if (onNavigateToActiveRun) {
        onNavigateToActiveRun(newRun.id);
      }
    } catch (err: any) {
      alert(err?.response?.data?.detail || 'Failed to start fix verification.');
    } finally {
      setVerifying(false);
    }
  };

  const selectedRun = runs.find((r) => r.id === selectedRunId);

  const filteredReports = reports.filter((r) => {
    if (filter === 'ALL') return true;
    return r.outcome_classification === filter;
  });

  const getClassificationBadge = (classification: string) => {
    switch (classification) {
      case 'CONSISTENTLY_PASSING':
        return (
          <span className="inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-md text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            <CheckCircle2 className="w-3.5 h-3.5" />
            <span>Consistently Passing</span>
          </span>
        );
      case 'CONSISTENTLY_FAILING':
        return (
          <span className="inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-md text-xs font-semibold bg-rose-500/10 text-rose-400 border border-rose-500/20">
            <XCircle className="w-3.5 h-3.5" />
            <span>Consistently Failing</span>
          </span>
        );
      case 'FLAKY':
        return (
          <span className="inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-md text-xs font-semibold bg-amber-500/10 text-amber-400 border border-amber-500/20">
            <AlertTriangle className="w-3.5 h-3.5" />
            <span>Flaky</span>
          </span>
        );
      case 'INSUFFICIENT_DATA':
      default:
        return (
          <span className="inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-md text-xs font-semibold bg-slate-500/10 text-slate-400 border border-slate-500/20">
            <HelpCircle className="w-3.5 h-3.5" />
            <span>Insufficient Data</span>
          </span>
        );
    }
  };

  const getRCACategoryBadge = (category?: string | null) => {
    if (!category) {
      return (
        <span className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-md text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
          <CheckCircle2 className="w-3.5 h-3.5" />
          <span>Stable / Deterministic Pass</span>
        </span>
      );
    }

    switch (category) {
      case 'ORDER_DEPENDENCY':
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-md text-xs font-semibold bg-purple-500/10 text-purple-400 border border-purple-500/30">
            <GitBranch className="w-3.5 h-3.5" />
            <span>Order Dependency</span>
          </span>
        );
      case 'SHARED_STATE_POLLUTION':
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-md text-xs font-semibold bg-indigo-500/10 text-indigo-400 border border-indigo-500/30">
            <Info className="w-3.5 h-3.5" />
            <span>Shared State Pollution</span>
          </span>
        );
      case 'TIMING_OR_RACE_CONDITION':
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-md text-xs font-semibold bg-amber-500/10 text-amber-400 border border-amber-500/30">
            <Clock className="w-3.5 h-3.5" />
            <span>Timing / Race Condition</span>
          </span>
        );
      case 'RESOURCE_EXHAUSTION':
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-md text-xs font-semibold bg-red-500/10 text-red-400 border border-red-500/30">
            <Cpu className="w-3.5 h-3.5" />
            <span>Resource Exhaustion</span>
          </span>
        );
      case 'ENVIRONMENT_DEPENDENCY':
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-md text-xs font-semibold bg-cyan-500/10 text-cyan-400 border border-cyan-500/30">
            <Terminal className="w-3.5 h-3.5" />
            <span>Environment Dependency</span>
          </span>
        );
      case 'EXTERNAL_DEPENDENCY':
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-md text-xs font-semibold bg-orange-500/10 text-orange-400 border border-orange-500/30">
            <Globe className="w-3.5 h-3.5" />
            <span>External Dependency</span>
          </span>
        );
      case 'ASSERTION_OR_LOGIC_FAILURE':
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-md text-xs font-semibold bg-rose-500/10 text-rose-400 border border-rose-500/30">
            <Bug className="w-3.5 h-3.5" />
            <span>Assertion / Logic Failure</span>
          </span>
        );
      case 'UNKNOWN':
      default:
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-md text-xs font-semibold bg-slate-800 text-slate-400 border border-slate-700">
            <HelpCircle className="w-3.5 h-3.5" />
            <span>Unknown / Inconclusive</span>
          </span>
        );
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedLog(true);
    setTimeout(() => setCopiedLog(false), 2000);
  };

  return (
    <div className="space-y-6">
      {/* Header with Run Selector */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-4 border-b border-slate-800">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight flex items-center space-x-2">
            <FileBarChart2 className="w-6 h-6 text-sky-400" />
            <span>Detailed Flakiness & RCA Reports</span>
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Comprehensive per-test execution telemetry, multi-iteration logs, and evidence-based root cause analysis.
          </p>
        </div>

        {runs.length > 0 && (
          <div className="flex flex-wrap items-center gap-2">
            <select
              value={selectedRunId}
              onChange={(e) => setSelectedRunId(e.target.value)}
              className="bg-slate-900 border border-slate-800 text-slate-200 text-xs rounded-lg px-3 py-2 focus:ring-1 focus:ring-sky-500 focus:outline-none"
            >
              {runs.map((r, idx) => (
                <option key={r.id} value={r.id}>
                  {r.project_name ? `${r.project_name} - ` : ''}
                  Run #{runs.length - idx} ({r.status}) - {r.iteration_count} iters - {r.id.slice(0, 8)}
                </option>
              ))}
            </select>

            <button
              onClick={handleAnalyze}
              disabled={analyzing || selectedRun?.status === 'RUNNING'}
              className="inline-flex items-center space-x-1.5 px-3 py-2 bg-slate-800 hover:bg-slate-700 disabled:opacity-50 text-slate-200 rounded-lg text-xs font-medium transition-colors border border-slate-700"
              title={
                selectedRun?.status === 'RUNNING'
                  ? 'Cannot analyze while run is running'
                  : 'Recompute flakiness analysis & RCA'
              }
            >
              <RefreshCw className={`w-3.5 h-3.5 ${analyzing ? 'animate-spin' : ''}`} />
              <span>{analyzing ? 'Analyzing...' : 'Re-Diagnose'}</span>
            </button>
          </div>
        )}
      </div>

      {/* Tri-Bucket Taxonomy Filter Tabs */}
      <div className="flex flex-wrap gap-2 pb-2">
        <button
          onClick={() => setFilter('ALL')}
          className={`flex items-center space-x-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
            filter === 'ALL'
              ? 'bg-sky-600 text-white'
              : 'bg-slate-800/60 text-slate-300 hover:bg-slate-800'
          }`}
        >
          <Filter className="w-3.5 h-3.5" />
          <span>All Tests ({reports.length})</span>
        </button>

        <button
          onClick={() => setFilter('FLAKY')}
          className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
            filter === 'FLAKY'
              ? 'bg-amber-600 text-white'
              : 'bg-slate-800/60 text-amber-400 hover:bg-slate-800'
          }`}
        >
          <AlertTriangle className="w-3.5 h-3.5" />
          <span>
            Flaky ({reports.filter((r) => r.outcome_classification === 'FLAKY').length})
          </span>
        </button>

        <button
          onClick={() => setFilter('FAILING')}
          className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
            filter === 'FAILING'
              ? 'bg-rose-600 text-white'
              : 'bg-slate-800/60 text-rose-400 hover:bg-slate-800'
          }`}
        >
          <XCircle className="w-3.5 h-3.5" />
          <span>
            Consistently Failing (
            {reports.filter((r) => r.outcome_classification === 'CONSISTENTLY_FAILING').length})
          </span>
        </button>

        <button
          onClick={() => setFilter('PASSING')}
          className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
            filter === 'PASSING'
              ? 'bg-emerald-600 text-white'
              : 'bg-slate-800/60 text-emerald-400 hover:bg-slate-800'
          }`}
        >
          <CheckCircle2 className="w-3.5 h-3.5" />
          <span>
            Consistently Passing (
            {reports.filter((r) => r.outcome_classification === 'CONSISTENTLY_PASSING').length})
          </span>
        </button>

        <button
          onClick={() => setFilter('INSUFFICIENT_DATA')}
          className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
            filter === 'INSUFFICIENT_DATA'
              ? 'bg-slate-600 text-white'
              : 'bg-slate-800/60 text-slate-400 hover:bg-slate-800'
          }`}
        >
          <HelpCircle className="w-3.5 h-3.5" />
          <span>
            Insufficient Data (
            {reports.filter((r) => r.outcome_classification === 'INSUFFICIENT_DATA').length})
          </span>
        </button>
      </div>

      {/* Reports Content Area */}
      {loading ? (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-12 text-center text-slate-400 text-sm">
          <Activity className="w-6 h-6 animate-spin mx-auto mb-2 text-sky-400" />
          Loading detailed reports and per-test execution telemetry...
        </div>
      ) : runs.length === 0 || reports.length === 0 ? (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
          <EmptyState
            icon={FileBarChart2}
            title="No Flakiness Reports Available"
            description="Reports and evidence-based Root Cause Analysis (RCA) will be synthesized here after tests are executed across multiple iterations."
            actionLabel="Execute Test Suite"
            onAction={onNavigateToNew}
          />
        </div>
      ) : filteredReports.length === 0 ? (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-8 text-center text-slate-400 text-sm">
          No test reports match the selected filter <span className="font-semibold text-slate-300">"{filter}"</span>.
        </div>
      ) : (
        <div className="space-y-4">
          {filteredReports.map((report) => {
            const evidence = report.supporting_evidence;
            const suspects = evidence?.suspect_preceding_tests || [];
            const isFlakyOrFailing =
              report.outcome_classification === 'FLAKY' ||
              report.outcome_classification === 'CONSISTENTLY_FAILING';

            return (
              <div
                key={report.id}
                className="p-5 rounded-xl bg-slate-900 border border-slate-800 hover:border-slate-700 transition-colors space-y-4"
              >
                {/* Top Header: Node ID, Outcome Classification & Verify Fix Button */}
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                  <div className="space-y-1">
                    <div className="font-mono text-sm font-semibold text-white break-all">
                      {report.node_id || report.test_name || `Test Case #${report.test_case_id.slice(0, 8)}`}
                    </div>
                    {report.file_path && (
                      <div className="text-xs text-slate-400 font-mono">{report.file_path}</div>
                    )}
                  </div>
                  <div className="flex items-center space-x-2">
                    {getClassificationBadge(report.outcome_classification)}
                    {isFlakyOrFailing && (
                      <button
                        onClick={() => setVerifyModalTest(report)}
                        className="inline-flex items-center space-x-1.5 px-3 py-1 bg-purple-600 hover:bg-purple-500 text-white rounded-md text-xs font-medium transition-colors shadow-sm"
                      >
                        <ShieldCheck className="w-3.5 h-3.5" />
                        <span>Verify Fix</span>
                      </button>
                    )}
                  </div>
                </div>

                {/* Metric Chips */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <div className="bg-slate-800/40 border border-slate-800 rounded-lg p-2.5">
                    <div className="text-[11px] uppercase tracking-wider text-slate-400 font-medium">
                      Valid Executions
                    </div>
                    <div className="text-sm font-semibold text-slate-200 mt-0.5">
                      {report.total_runs} runs
                    </div>
                  </div>

                  <div className="bg-slate-800/40 border border-slate-800 rounded-lg p-2.5">
                    <div className="text-[11px] uppercase tracking-wider text-slate-400 font-medium">
                      Pass / Fail Count
                    </div>
                    <div className="text-sm font-semibold text-slate-200 mt-0.5">
                      <span className="text-emerald-400">{report.pass_count}P</span>
                      {' / '}
                      <span className="text-rose-400">{report.fail_count}F</span>
                    </div>
                  </div>

                  <div className="bg-slate-800/40 border border-slate-800 rounded-lg p-2.5">
                    <div className="text-[11px] uppercase tracking-wider text-slate-400 font-medium">
                      Flakiness Score (F)
                    </div>
                    <div className="text-sm font-semibold text-slate-200 mt-0.5">
                      {report.outcome_classification === 'INSUFFICIENT_DATA'
                        ? 'N/A'
                        : `${(report.flakiness_score * 100).toFixed(1)}% (F = ${report.flakiness_score.toFixed(4)})`}
                    </div>
                  </div>

                  <div className="bg-slate-800/40 border border-slate-800 rounded-lg p-2.5">
                    <div className="text-[11px] uppercase tracking-wider text-slate-400 font-medium">
                      Flip Count (κ)
                    </div>
                    <div className="text-sm font-semibold text-slate-200 mt-0.5">
                      {report.flip_count} transitions
                    </div>
                  </div>
                </div>

                {/* Per-Test Execution History / Iteration Breakdown */}
                {report.iterations && report.iterations.length > 0 && (
                  <div className="p-3 bg-slate-950/40 border border-slate-800 rounded-lg space-y-2">
                    <div className="flex items-center justify-between text-xs text-slate-400">
                      <span className="font-semibold uppercase tracking-wider text-slate-300">
                        Execution Timeline ({report.iterations.length} iterations)
                      </span>
                      <span className="text-[11px] text-slate-500">
                        Click any iteration to inspect console logs & traceback
                      </span>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {report.iterations.map((it) => (
                        <button
                          key={it.iteration_number}
                          onClick={() => setSelectedIteration({ test: report, iteration: it })}
                          className={`px-2 py-1 rounded text-[11px] font-mono border transition-all flex items-center space-x-1 ${
                            it.status === 'PASSED'
                              ? 'bg-emerald-950/40 border-emerald-800/60 text-emerald-300 hover:bg-emerald-900/60'
                              : it.status === 'TIMED_OUT'
                              ? 'bg-red-950/40 border-red-800/60 text-red-300 hover:bg-red-900/60'
                              : 'bg-rose-950/40 border-rose-800/60 text-rose-300 hover:bg-rose-900/60'
                          }`}
                        >
                          <span className="font-bold">#{it.iteration_number}</span>
                          <span>
                            {it.status === 'PASSED' ? '✓' : it.status === 'TIMED_OUT' ? '⏱' : '✗'}
                          </span>
                          <span className="text-[10px] opacity-75">
                            {it.duration_ms ? `${it.duration_ms.toFixed(0)}ms` : ''}
                          </span>
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {/* Root Cause Analysis (RCA) Section */}
                <div className="mt-3 pt-3 border-t border-slate-800/80 space-y-3">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                    <div className="flex items-center space-x-2">
                      <span className="text-xs font-semibold uppercase tracking-wider text-slate-300">
                        Root Cause Diagnosis:
                      </span>
                      {getRCACategoryBadge(report.root_cause_category)}
                    </div>

                    <div className="flex items-center space-x-2">
                      <span className="text-xs text-slate-400">Evidence Confidence:</span>
                      {report.root_cause_category ? (
                        <div className="flex items-center space-x-1.5 bg-slate-800/60 px-2 py-0.5 rounded border border-slate-700/60 text-xs font-medium text-slate-200">
                          <div
                            className={`w-2 h-2 rounded-full ${
                              (report.confidence_score ?? 0) >= 0.7
                                ? 'bg-emerald-400'
                                : (report.confidence_score ?? 0) >= 0.4
                                ? 'bg-amber-400'
                                : 'bg-slate-400'
                            }`}
                          />
                          <span>{((report.confidence_score ?? 0) * 100).toFixed(0)}%</span>
                        </div>
                      ) : (
                        <span className="text-xs text-slate-500 font-mono">
                          N/A (Deterministic Pass)
                        </span>
                      )}
                    </div>
                  </div>

                  {/* RCA Structured Summary */}
                  {report.rca_summary && (
                    <div className="p-3.5 bg-slate-950/60 border border-slate-800 rounded-lg text-xs text-slate-300 font-mono whitespace-pre-line leading-relaxed">
                      {report.rca_summary}
                    </div>
                  )}

                  {/* Actionable Recommendations */}
                  {report.recommendations && (
                    <div className="p-3 bg-sky-950/20 border border-sky-800/30 rounded-lg text-xs text-sky-200 space-y-1">
                      <div className="flex items-center space-x-1.5 font-semibold text-sky-400">
                        <Wrench className="w-3.5 h-3.5" />
                        <span>Actionable Recommendations</span>
                      </div>
                      <p className="whitespace-pre-line text-slate-300 font-sans leading-relaxed">
                        {report.recommendations}
                      </p>
                    </div>
                  )}

                  {/* Suspected Preceding Tests */}
                  {suspects.length > 0 && (
                    <div className="p-3 bg-purple-950/20 border border-purple-800/30 rounded-lg text-xs space-y-1.5">
                      <div className="flex items-center space-x-1.5 font-semibold text-purple-300">
                        <GitBranch className="w-3.5 h-3.5" />
                        <span>
                          Suspected Preceding Tests (Permutation Correlation) ({suspects.length})
                        </span>
                      </div>
                      <div className="space-y-1">
                        {suspects.map((s: any, sIdx: number) => (
                          <div
                            key={sIdx}
                            className="flex flex-col sm:flex-row sm:items-center justify-between text-slate-300 font-mono text-[11px] bg-slate-900/60 p-1.5 rounded border border-purple-900/40"
                          >
                            <span className="text-purple-200 truncate">{s.node_id}</span>
                            <span className="text-slate-400">
                              Preceded {s.preceded_in_failures}/{report.fail_count} failures (
                              {s.preceded_in_passes} passes) • Correlation:{' '}
                              {(s.correlation_score * 100).toFixed(0)}% • Candidate Polluter
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* MODAL 1: Iteration Log Inspector */}
      {selectedIteration && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-xl max-w-3xl w-full max-h-[85vh] flex flex-col shadow-2xl">
            {/* Modal Header */}
            <div className="p-4 border-b border-slate-800 flex items-center justify-between">
              <div>
                <h3 className="font-semibold text-white text-sm flex items-center space-x-2">
                  <Terminal className="w-4 h-4 text-sky-400" />
                  <span>
                    Iteration #{selectedIteration.iteration.iteration_number} Telemetry Details
                  </span>
                  <span
                    className={`px-2 py-0.5 rounded text-[11px] font-bold ${
                      selectedIteration.iteration.status === 'PASSED'
                        ? 'bg-emerald-500/20 text-emerald-400'
                        : 'bg-rose-500/20 text-rose-400'
                    }`}
                  >
                    {selectedIteration.iteration.status}
                  </span>
                </h3>
                <p className="text-xs text-slate-400 font-mono mt-0.5 truncate max-w-xl">
                  {selectedIteration.test.node_id}
                </p>
              </div>
              <button
                onClick={() => setSelectedIteration(null)}
                className="p-1 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Body: Metadata Chips & Logs */}
            <div className="p-4 space-y-4 overflow-y-auto flex-1 font-mono text-xs">
              <div className="grid grid-cols-3 gap-2 text-slate-300">
                <div className="p-2 bg-slate-800/50 rounded border border-slate-700/60">
                  <span className="text-slate-400 text-[10px] block uppercase">Duration</span>
                  <span className="font-bold">{selectedIteration.iteration.duration_ms.toFixed(1)} ms</span>
                </div>
                <div className="p-2 bg-slate-800/50 rounded border border-slate-700/60">
                  <span className="text-slate-400 text-[10px] block uppercase">Execution Order</span>
                  <span className="font-bold">Position #{selectedIteration.iteration.execution_order}</span>
                </div>
                <div className="p-2 bg-slate-800/50 rounded border border-slate-700/60">
                  <span className="text-slate-400 text-[10px] block uppercase">Random Seed</span>
                  <span className="font-bold">{selectedIteration.iteration.random_order_seed ?? 'None'}</span>
                </div>
              </div>

              {/* Error Message */}
              {selectedIteration.iteration.error_message && (
                <div className="space-y-1">
                  <div className="text-rose-400 font-semibold flex items-center justify-between">
                    <span>Error Message</span>
                  </div>
                  <pre className="p-3 bg-rose-950/30 border border-rose-900/40 rounded text-rose-300 whitespace-pre-wrap break-all">
                    {selectedIteration.iteration.error_message}
                  </pre>
                </div>
              )}

              {/* Traceback */}
              {selectedIteration.iteration.traceback && (
                <div className="space-y-1">
                  <div className="text-slate-300 font-semibold flex items-center justify-between">
                    <span>Failure Traceback</span>
                    <button
                      onClick={() => copyToClipboard(selectedIteration.iteration.traceback || '')}
                      className="text-[11px] text-slate-400 hover:text-white flex items-center space-x-1"
                    >
                      {copiedLog ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                      <span>{copiedLog ? 'Copied' : 'Copy'}</span>
                    </button>
                  </div>
                  <pre className="p-3 bg-slate-950 border border-slate-800 rounded text-slate-300 whitespace-pre-wrap break-all max-h-60 overflow-y-auto">
                    {selectedIteration.iteration.traceback}
                  </pre>
                </div>
              )}

              {/* Stdout */}
              {selectedIteration.iteration.stdout && (
                <div className="space-y-1">
                  <div className="text-slate-300 font-semibold">Standard Output (stdout)</div>
                  <pre className="p-3 bg-slate-950 border border-slate-800 rounded text-slate-400 whitespace-pre-wrap break-all max-h-40 overflow-y-auto">
                    {selectedIteration.iteration.stdout}
                  </pre>
                </div>
              )}

              {/* Stderr */}
              {selectedIteration.iteration.stderr && (
                <div className="space-y-1">
                  <div className="text-slate-300 font-semibold">Standard Error (stderr)</div>
                  <pre className="p-3 bg-slate-950 border border-slate-800 rounded text-amber-300/80 whitespace-pre-wrap break-all max-h-40 overflow-y-auto">
                    {selectedIteration.iteration.stderr}
                  </pre>
                </div>
              )}
            </div>

            <div className="p-3 border-t border-slate-800 flex justify-end">
              <button
                onClick={() => setSelectedIteration(null)}
                className="px-4 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg text-xs font-medium"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* MODAL 2: Fix Verification Launcher */}
      {verifyModalTest && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-xl max-w-lg w-full p-6 space-y-5 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center space-x-2">
                <ShieldCheck className="w-5 h-5 text-purple-400" />
                <h3 className="font-semibold text-white text-base">Verify Test Fix</h3>
              </div>
              <button
                onClick={() => setVerifyModalTest(null)}
                className="p-1 text-slate-400 hover:text-white rounded hover:bg-slate-800"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-3 text-xs text-slate-300">
              <p className="text-slate-400">
                Execute a targeted, multi-iteration verification run in isolated Docker containers to
                empirically prove this test is stable across repeated executions.
              </p>

              <div className="p-3 bg-slate-800/50 rounded-lg border border-slate-700 space-y-1 font-mono">
                <span className="text-[10px] text-purple-400 uppercase font-bold block">
                  Targeted Test Case
                </span>
                <span className="text-white text-xs break-all">{verifyModalTest.node_id}</span>
                <div className="text-slate-400 text-[11px] pt-1">
                  Prior Outcome: {verifyModalTest.outcome_classification} (F={verifyModalTest.flakiness_score.toFixed(4)})
                </div>
              </div>

              {/* Iteration Count */}
              <div className="space-y-1">
                <label className="font-medium text-slate-300 flex justify-between">
                  <span>Verification Iterations (Minimum 5 required):</span>
                  <span className="font-bold text-sky-400">{verifyIterations} iterations</span>
                </label>
                <input
                  type="range"
                  min={5}
                  max={30}
                  step={1}
                  value={verifyIterations}
                  onChange={(e) => setVerifyIterations(parseInt(e.target.value, 10))}
                  className="w-full accent-sky-500"
                />
              </div>

              {/* Shuffling Toggle */}
              <label className="flex items-center space-x-2 pt-1 cursor-pointer">
                <input
                  type="checkbox"
                  checked={verifyShuffle}
                  onChange={(e) => setVerifyShuffle(e.target.checked)}
                  className="rounded border-slate-700 bg-slate-800 text-sky-500 focus:ring-0"
                />
                <span className="text-slate-300 font-medium">
                  Enable pytest random execution order shuffling
                </span>
              </label>

              <div className="p-3 bg-amber-950/20 border border-amber-900/30 rounded text-[11px] text-amber-300/90 leading-relaxed">
                <AlertTriangle className="w-3.5 h-3.5 inline mr-1 text-amber-400" />
                FLAKELENS requires at least 5 consecutive passing executions with zero flips to mark a fix verified. Single-pass runs will not mark the test fixed.
              </div>
            </div>

            <div className="flex items-center justify-end space-x-3 pt-3 border-t border-slate-800">
              <button
                type="button"
                onClick={() => setVerifyModalTest(null)}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-xs font-medium"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleLaunchVerification}
                disabled={verifying}
                className="inline-flex items-center space-x-1.5 px-4 py-2 bg-purple-600 hover:bg-purple-500 text-white rounded-lg text-xs font-semibold shadow-sm transition-colors disabled:opacity-50"
              >
                {verifying ? (
                  <>
                    <Activity className="w-3.5 h-3.5 animate-spin" />
                    <span>Launching...</span>
                  </>
                ) : (
                  <>
                    <Play className="w-3.5 h-3.5 fill-white" />
                    <span>Launch Verification Run</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
