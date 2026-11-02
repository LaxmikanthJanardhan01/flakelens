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
          <span className="inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-md text-xs font-semibold bg-[#EBF8F2] text-[#159B67] border border-[#A7E7CB]">
            <CheckCircle2 className="w-3.5 h-3.5" />
            <span>Consistently Passing</span>
          </span>
        );
      case 'CONSISTENTLY_FAILING':
        return (
          <span className="inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-md text-xs font-semibold bg-[#FDF2F2] text-[#DC4B4B] border border-[#F7BEBE]">
            <XCircle className="w-3.5 h-3.5" />
            <span>Consistently Failing</span>
          </span>
        );
      case 'FLAKY':
        return (
          <span className="inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-md text-xs font-semibold bg-[#FEF8EC] text-[#D99A22] border border-[#FADDA8]">
            <AlertTriangle className="w-3.5 h-3.5" />
            <span>Flaky</span>
          </span>
        );
      case 'INSUFFICIENT_DATA':
      default:
        return (
          <span className="inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-md text-xs font-semibold bg-[#F1F3F7] text-[#647084] border border-[#E5E9E8]">
            <HelpCircle className="w-3.5 h-3.5" />
            <span>Insufficient Data</span>
          </span>
        );
    }
  };

  const getRCACategoryBadge = (category?: string | null) => {
    if (!category) {
      return (
        <span className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-md text-xs font-medium bg-[#EBF8F2] text-[#159B67] border border-[#A7E7CB]">
          <CheckCircle2 className="w-3.5 h-3.5" />
          <span>Stable / Deterministic Pass</span>
        </span>
      );
    }

    switch (category) {
      case 'ORDER_DEPENDENCY':
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-md text-xs font-semibold bg-[#FEF8EC] text-[#D99A22] border border-[#FADDA8]">
            <GitBranch className="w-3.5 h-3.5" />
            <span>Order Dependency</span>
          </span>
        );
      case 'SHARED_STATE_POLLUTION':
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-md text-xs font-semibold bg-[#FEF8EC] text-[#D99A22] border border-[#FADDA8]">
            <Info className="w-3.5 h-3.5" />
            <span>Shared State Pollution</span>
          </span>
        );
      case 'TIMING_OR_RACE_CONDITION':
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-md text-xs font-semibold bg-[#FEF8EC] text-[#D99A22] border border-[#FADDA8]">
            <Clock className="w-3.5 h-3.5" />
            <span>Timing / Race Condition</span>
          </span>
        );
      case 'RESOURCE_EXHAUSTION':
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-md text-xs font-semibold bg-[#FDF2F2] text-[#DC4B4B] border border-[#F7BEBE]">
            <Cpu className="w-3.5 h-3.5" />
            <span>Resource Exhaustion</span>
          </span>
        );
      case 'ENVIRONMENT_DEPENDENCY':
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-md text-xs font-semibold bg-[#F0FDFA] text-[#0F766E] border border-[#CCFBF1]">
            <Terminal className="w-3.5 h-3.5" />
            <span>Environment Dependency</span>
          </span>
        );
      case 'EXTERNAL_DEPENDENCY':
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-md text-xs font-semibold bg-[#FEF8EC] text-[#D99A22] border border-[#FADDA8]">
            <Globe className="w-3.5 h-3.5" />
            <span>External Dependency</span>
          </span>
        );
      case 'ASSERTION_OR_LOGIC_FAILURE':
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-md text-xs font-semibold bg-[#FDF2F2] text-[#DC4B4B] border border-[#F7BEBE]">
            <Bug className="w-3.5 h-3.5" />
            <span>Assertion / Logic Failure</span>
          </span>
        );
      case 'UNKNOWN':
      default:
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-md text-xs font-semibold bg-[#F1F3F7] text-[#647084] border border-[#E5E9E8]">
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
    <div className="space-y-5">
      {/* Header with Run Selector */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-4 border-b border-[#E5E9E8]">
        <div>
          <h1 className="text-xl font-bold text-[#202A32] tracking-tight">Detailed Flakiness &amp; RCA Reports</h1>
          <p className="text-xs text-[#647084] mt-0.5">
            Comprehensive per-test execution telemetry, multi-iteration logs, and evidence-based root cause analysis.
          </p>
        </div>

        {runs.length > 0 && (
          <div className="flex flex-wrap items-center gap-2">
            <select
              value={selectedRunId}
              onChange={(e) => setSelectedRunId(e.target.value)}
              className="bg-[#FFFFFF] border border-[#E5E9E8] text-[#202A32] text-xs rounded-md px-3 py-2 focus:ring-1 focus:ring-[#0F766E] focus:border-[#0F766E] focus:outline-none"
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
              className="inline-flex items-center space-x-1.5 px-3 py-1.5 bg-[#FFFFFF] hover:bg-[#F7F8FA] disabled:opacity-50 text-[#202A32] rounded-md text-xs font-medium transition-colors border border-[#E5E9E8] cursor-pointer"
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

      {/* Filter Tabs */}
      <div className="flex flex-wrap gap-2 pb-2">
        <button
          onClick={() => setFilter('ALL')}
          className={`flex items-center space-x-2 px-3 py-1.5 rounded-md text-xs font-medium transition-colors cursor-pointer ${
            filter === 'ALL'
              ? 'bg-[#0F766E] text-white'
              : 'bg-[#F7F8FA] text-[#647084] hover:bg-[#F1F5F5] border border-[#E5E9E8]'
          }`}
        >
          <Filter className="w-3.5 h-3.5" />
          <span>All Tests ({reports.length})</span>
        </button>

        <button
          onClick={() => setFilter('FLAKY')}
          className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors cursor-pointer ${
            filter === 'FLAKY'
              ? 'bg-[#D99A22] text-white'
              : 'bg-[#FEF8EC] text-[#D99A22] hover:bg-[#FADDA8] border border-[#FADDA8]'
          }`}
        >
          <AlertTriangle className="w-3.5 h-3.5" />
          <span>
            Flaky ({reports.filter((r) => r.outcome_classification === 'FLAKY').length})
          </span>
        </button>

        <button
          onClick={() => setFilter('FAILING')}
          className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors cursor-pointer ${
            filter === 'FAILING'
              ? 'bg-[#DC4B4B] text-white'
              : 'bg-[#FDF2F2] text-[#DC4B4B] hover:bg-[#F7BEBE] border border-[#F7BEBE]'
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
          className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors cursor-pointer ${
            filter === 'PASSING'
              ? 'bg-[#159B67] text-white'
              : 'bg-[#EBF8F2] text-[#159B67] hover:bg-[#A7E7CB] border border-[#A7E7CB]'
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
          className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors cursor-pointer ${
            filter === 'INSUFFICIENT_DATA'
              ? 'bg-[#647084] text-white'
              : 'bg-[#F1F3F7] text-[#647084] hover:bg-[#E5E9E8] border border-[#E5E9E8]'
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
        <div className="bg-[#FFFFFF] border border-[#E5E9E8] rounded-lg p-12 text-center text-[#647084] text-sm">
          <Activity className="w-6 h-6 animate-spin mx-auto mb-2 text-[#0F766E]" />
          Loading detailed reports and per-test execution telemetry...
        </div>
      ) : runs.length === 0 || reports.length === 0 ? (
        <div className="bg-[#FFFFFF] border border-[#E5E9E8] rounded-lg p-6">
          <EmptyState
            icon={FileBarChart2}
            title="No Flakiness Reports Available"
            description="Reports and evidence-based Root Cause Analysis (RCA) will be synthesized here after tests are executed across multiple iterations."
            actionLabel="Execute Test Suite"
            onAction={onNavigateToNew}
          />
        </div>
      ) : filteredReports.length === 0 ? (
        <div className="bg-[#FFFFFF] border border-[#E5E9E8] rounded-lg p-8 text-center text-[#647084] text-sm">
          No test reports match the selected filter <span className="font-semibold text-[#202A32]">"{filter}"</span>.
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
                className="p-5 rounded-lg bg-[#FFFFFF] border border-[#E5E9E8] hover:border-[#CBD5E1] transition-colors space-y-4 shadow-card"
              >
                {/* Top Header */}
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                  <div className="space-y-1">
                    <div className="font-mono text-sm font-semibold text-[#202A32] break-all">
                      {report.node_id || report.test_name || `Test Case #${report.test_case_id.slice(0, 8)}`}
                    </div>
                    {report.file_path && (
                      <div className="text-xs text-[#647084] font-mono">{report.file_path}</div>
                    )}
                  </div>
                  <div className="flex items-center space-x-2">
                    {getClassificationBadge(report.outcome_classification)}
                    {isFlakyOrFailing && (
                      <button
                        onClick={() => setVerifyModalTest(report)}
                        className="inline-flex items-center space-x-1.5 px-3 py-1 bg-[#0F766E] hover:bg-[#0D6860] text-white rounded-md text-xs font-medium transition-colors shadow-sm cursor-pointer"
                      >
                        <ShieldCheck className="w-3.5 h-3.5" />
                        <span>Verify Fix</span>
                      </button>
                    )}
                  </div>
                </div>

                {/* Metric Chips */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <div className="bg-[#F7F8FA] border border-[#E5E9E8] rounded-md p-2.5">
                    <div className="text-[11px] uppercase tracking-wider text-[#647084] font-medium">
                      Valid Executions
                    </div>
                    <div className="text-sm font-semibold text-[#202A32] mt-0.5">
                      {report.total_runs} runs
                    </div>
                  </div>

                  <div className="bg-[#F7F8FA] border border-[#E5E9E8] rounded-md p-2.5">
                    <div className="text-[11px] uppercase tracking-wider text-[#647084] font-medium">
                      Pass / Fail Count
                    </div>
                    <div className="text-sm font-semibold text-[#202A32] mt-0.5">
                      <span className="text-[#159B67]">{report.pass_count}P</span>
                      {' / '}
                      <span className="text-[#DC4B4B]">{report.fail_count}F</span>
                    </div>
                  </div>

                  <div className="bg-[#F7F8FA] border border-[#E5E9E8] rounded-md p-2.5">
                    <div className="text-[11px] uppercase tracking-wider text-[#647084] font-medium">
                      Flakiness Score (F)
                    </div>
                    <div className="text-sm font-semibold text-[#202A32] mt-0.5">
                      {report.outcome_classification === 'INSUFFICIENT_DATA'
                        ? 'N/A'
                        : `${(report.flakiness_score * 100).toFixed(1)}% (F = ${report.flakiness_score.toFixed(4)})`}
                    </div>
                  </div>

                  <div className="bg-[#F7F8FA] border border-[#E5E9E8] rounded-md p-2.5">
                    <div className="text-[11px] uppercase tracking-wider text-[#647084] font-medium">
                      Flip Count (κ)
                    </div>
                    <div className="text-sm font-semibold text-[#202A32] mt-0.5">
                      {report.flip_count} transitions
                    </div>
                  </div>
                </div>

                {/* Per-Test Iteration History */}
                {report.iterations && report.iterations.length > 0 && (
                  <div className="p-3 bg-[#F7F8FA] border border-[#E5E9E8] rounded-md space-y-2">
                    <div className="flex items-center justify-between text-xs text-[#647084]">
                      <span className="font-semibold uppercase tracking-wider text-[#202A32]">
                        Execution Timeline ({report.iterations.length} iterations)
                      </span>
                      <span className="text-[11px] text-[#8993A2]">
                        Click any iteration to inspect console logs &amp; traceback
                      </span>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {report.iterations.map((it) => (
                        <button
                          key={it.iteration_number}
                          onClick={() => setSelectedIteration({ test: report, iteration: it })}
                          className={`px-2 py-1 rounded text-[11px] font-mono border transition-all flex items-center space-x-1 cursor-pointer ${
                            it.status === 'PASSED'
                              ? 'bg-[#EBF8F2] border-[#A7E7CB] text-[#159B67] hover:bg-[#A7E7CB]'
                              : it.status === 'TIMED_OUT'
                              ? 'bg-[#FEF8EC] border-[#FADDA8] text-[#D99A22] hover:bg-[#FADDA8]'
                              : 'bg-[#FDF2F2] border-[#F7BEBE] text-[#DC4B4B] hover:bg-[#F7BEBE]'
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

                {/* Root Cause Analysis Section */}
                <div className="mt-3 pt-3 border-t border-[#E5E9E8] space-y-3">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                    <div className="flex items-center space-x-2">
                      <span className="text-xs font-semibold uppercase tracking-wider text-[#202A32]">
                        Root Cause Diagnosis:
                      </span>
                      {getRCACategoryBadge(report.root_cause_category)}
                    </div>

                    <div className="flex items-center space-x-2">
                      <span className="text-xs text-[#647084]">Evidence Confidence:</span>
                      {report.root_cause_category ? (
                        <div className="flex items-center space-x-1.5 bg-[#F7F8FA] px-2 py-0.5 rounded border border-[#E5E9E8] text-xs font-medium text-[#202A32]">
                          <div
                            className={`w-2 h-2 rounded-full ${
                              (report.confidence_score ?? 0) >= 0.7
                                ? 'bg-[#159B67]'
                                : (report.confidence_score ?? 0) >= 0.4
                                ? 'bg-[#D99A22]'
                                : 'bg-[#8993A2]'
                            }`}
                          />
                          <span>{((report.confidence_score ?? 0) * 100).toFixed(0)}%</span>
                        </div>
                      ) : (
                        <span className="text-xs text-[#8993A2] font-mono">
                          N/A (Deterministic Pass)
                        </span>
                      )}
                    </div>
                  </div>

                  {/* RCA Summary */}
                  {report.rca_summary && (
                    <pre className="p-3 rounded-md bg-[#F1F3F7] border border-[#E5E9E8] text-[#202A32] font-mono text-[11px] overflow-x-auto whitespace-pre leading-relaxed">
                      {report.rca_summary}
                    </pre>
                  )}

                  {/* Actionable Recommendations */}
                  {report.recommendations && (
                    <div className="p-3 bg-[#F0FDFA] border border-[#CCFBF1] rounded-md text-xs text-[#202A32] space-y-1">
                      <div className="flex items-center space-x-1.5 font-semibold text-[#0F766E]">
                        <Wrench className="w-3.5 h-3.5" />
                        <span>Actionable Recommendations</span>
                      </div>
                      <p className="whitespace-pre-line text-[#647084] font-sans leading-relaxed">
                        {report.recommendations}
                      </p>
                    </div>
                  )}

                  {/* Suspected Preceding Tests */}
                  {suspects.length > 0 && (
                    <div className="p-3 bg-[#F0FDFA] border border-[#CCFBF1] rounded-md text-xs space-y-1.5">
                      <div className="flex items-center space-x-1.5 font-semibold text-[#0F766E]">
                        <GitBranch className="w-3.5 h-3.5" />
                        <span>
                          Suspected Preceding Tests (Permutation Correlation) ({suspects.length})
                        </span>
                      </div>
                      <div className="space-y-1">
                        {suspects.map((s: any, sIdx: number) => (
                          <div
                            key={sIdx}
                            className="flex flex-col sm:flex-row sm:items-center justify-between text-[#202A32] font-mono text-[11px] bg-[#FFFFFF] p-1.5 rounded border border-[#CCFBF1]"
                          >
                            <span className="text-[#0F766E] truncate">{s.node_id}</span>
                            <span className="text-[#647084]">
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
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-[#FFFFFF] border border-[#E5E9E8] rounded-lg max-w-3xl w-full max-h-[85vh] flex flex-col shadow-modal">
            {/* Modal Header */}
            <div className="p-4 border-b border-[#E5E9E8] flex items-center justify-between">
              <div>
                <h3 className="font-semibold text-[#202A32] text-sm flex items-center space-x-2">
                  <Terminal className="w-4 h-4 text-[#0F766E]" />
                  <span>
                    Iteration #{selectedIteration.iteration.iteration_number} Telemetry Details
                  </span>
                  <span
                    className={`px-2 py-0.5 rounded text-[11px] font-bold ${
                      selectedIteration.iteration.status === 'PASSED'
                        ? 'bg-[#EBF8F2] text-[#159B67] border border-[#A7E7CB]'
                        : 'bg-[#FDF2F2] text-[#DC4B4B] border border-[#F7BEBE]'
                    }`}
                  >
                    {selectedIteration.iteration.status}
                  </span>
                </h3>
                <p className="text-xs text-[#647084] font-mono mt-0.5 truncate max-w-xl">
                  {selectedIteration.test.node_id}
                </p>
              </div>
              <button
                onClick={() => setSelectedIteration(null)}
                className="p-1 text-[#647084] hover:text-[#202A32] rounded-md hover:bg-[#F7F8FA] cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-4 space-y-4 overflow-y-auto flex-1 font-mono text-xs">
              <div className="grid grid-cols-3 gap-2 text-[#202A32]">
                <div className="p-2 bg-[#F7F8FA] rounded border border-[#E5E9E8]">
                  <span className="text-[#647084] text-[10px] block uppercase">Duration</span>
                  <span className="font-bold">{selectedIteration.iteration.duration_ms.toFixed(1)} ms</span>
                </div>
                <div className="p-2 bg-[#F7F8FA] rounded border border-[#E5E9E8]">
                  <span className="text-[#647084] text-[10px] block uppercase">Execution Order</span>
                  <span className="font-bold">Position #{selectedIteration.iteration.execution_order}</span>
                </div>
                <div className="p-2 bg-[#F7F8FA] rounded border border-[#E5E9E8]">
                  <span className="text-[#647084] text-[10px] block uppercase">Random Seed</span>
                  <span className="font-bold">{selectedIteration.iteration.random_order_seed ?? 'None'}</span>
                </div>
              </div>

              {/* Error Message */}
              {selectedIteration.iteration.error_message && (
                <div className="space-y-1">
                  <div className="text-[#DC4B4B] font-semibold flex items-center justify-between">
                    <span>Error Message</span>
                  </div>
                  <pre className="p-3 rounded-md bg-[#FDF2F2] border border-[#F7BEBE] text-[#DC4B4B] font-mono text-[11px] overflow-x-auto whitespace-pre">
                    {selectedIteration.iteration.error_message}
                  </pre>
                </div>
              )}

              {/* Traceback */}
              {selectedIteration.iteration.traceback && (
                <div className="space-y-1">
                  <div className="text-[#202A32] font-semibold flex items-center justify-between">
                    <span>Failure Traceback</span>
                    <button
                      onClick={() => copyToClipboard(selectedIteration.iteration.traceback || '')}
                      className="text-[11px] text-[#647084] hover:text-[#202A32] flex items-center space-x-1 cursor-pointer"
                    >
                      {copiedLog ? <Check className="w-3 h-3 text-[#159B67]" /> : <Copy className="w-3 h-3" />}
                      <span>{copiedLog ? 'Copied' : 'Copy'}</span>
                    </button>
                  </div>
                  <pre className="p-3 rounded-md bg-[#F1F3F7] border border-[#E5E9E8] text-[#202A32] font-mono text-[11px] overflow-x-auto whitespace-pre max-h-60 overflow-y-auto">
                    {selectedIteration.iteration.traceback}
                  </pre>
                </div>
              )}

              {/* Stdout */}
              {selectedIteration.iteration.stdout && (
                <div className="space-y-1">
                  <div className="text-[#202A32] font-semibold">Standard Output (stdout)</div>
                  <pre className="p-3 rounded-md bg-[#F1F3F7] border border-[#E5E9E8] text-[#202A32] font-mono text-[11px] overflow-x-auto whitespace-pre max-h-40 overflow-y-auto">
                    {selectedIteration.iteration.stdout}
                  </pre>
                </div>
              )}

              {/* Stderr */}
              {selectedIteration.iteration.stderr && (
                <div className="space-y-1">
                  <div className="text-[#202A32] font-semibold">Standard Error (stderr)</div>
                  <pre className="p-3 rounded-md bg-[#FDF2F2] border border-[#F7BEBE] text-[#DC4B4B] font-mono text-[11px] overflow-x-auto whitespace-pre max-h-40 overflow-y-auto">
                    {selectedIteration.iteration.stderr}
                  </pre>
                </div>
              )}
            </div>

            <div className="p-3 border-t border-[#E5E9E8] flex justify-end">
              <button
                onClick={() => setSelectedIteration(null)}
                className="px-4 py-1.5 bg-[#FFFFFF] hover:bg-[#F7F8FA] text-[#202A32] border border-[#E5E9E8] rounded-md text-xs font-medium cursor-pointer"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* MODAL 2: Fix Verification Launcher */}
      {verifyModalTest && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-[#FFFFFF] border border-[#E5E9E8] rounded-lg max-w-lg w-full p-6 space-y-5 shadow-modal">
            <div className="flex items-center justify-between border-b border-[#E5E9E8] pb-3">
              <div className="flex items-center space-x-2">
                <ShieldCheck className="w-5 h-5 text-[#0F766E]" />
                <h3 className="font-semibold text-[#202A32] text-base">Verify Test Fix</h3>
              </div>
              <button
                onClick={() => setVerifyModalTest(null)}
                className="p-1 text-[#647084] hover:text-[#202A32] rounded hover:bg-[#F7F8FA] cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-3 text-xs text-[#202A32]">
              <p className="text-[#647084]">
                Execute a targeted, multi-iteration verification run in isolated Docker containers to
                empirically prove this test is stable across repeated executions.
              </p>

              <div className="p-3 bg-[#F7F8FA] rounded-md border border-[#E5E9E8] space-y-1 font-mono">
                <span className="text-[10px] text-[#0F766E] uppercase font-bold block">
                  Targeted Test Case
                </span>
                <span className="text-[#202A32] text-xs break-all">{verifyModalTest.node_id}</span>
                <div className="text-[#647084] text-[11px] pt-1">
                  Prior Outcome: {verifyModalTest.outcome_classification} (F={verifyModalTest.flakiness_score.toFixed(4)})
                </div>
              </div>

              {/* Iteration Count */}
              <div className="space-y-1">
                <label className="font-medium text-[#202A32] flex justify-between">
                  <span>Verification Iterations (Minimum 5 required):</span>
                  <span className="font-bold text-[#0F766E]">{verifyIterations} iterations</span>
                </label>
                <input
                  type="range"
                  min={5}
                  max={30}
                  step={1}
                  value={verifyIterations}
                  onChange={(e) => setVerifyIterations(parseInt(e.target.value, 10))}
                  className="w-full accent-[#0F766E] bg-[#E5E9E8] rounded"
                />
              </div>

              {/* Shuffling Toggle */}
              <label className="flex items-center space-x-2 pt-1 cursor-pointer">
                <input
                  type="checkbox"
                  checked={verifyShuffle}
                  onChange={(e) => setVerifyShuffle(e.target.checked)}
                  className="rounded border-[#E5E9E8] text-[#0F766E] focus:ring-0"
                />
                <span className="text-[#202A32] font-medium">
                  Enable pytest random execution order shuffling
                </span>
              </label>

              <div className="p-3 bg-[#FEF8EC] border border-[#FADDA8] rounded text-[11px] text-[#D99A22] leading-relaxed">
                <AlertTriangle className="w-3.5 h-3.5 inline mr-1 text-[#D99A22]" />
                FLAKELENS requires at least 5 consecutive passing executions with zero flips to mark a fix verified. Single-pass runs will not mark the test fixed.
              </div>
            </div>

            <div className="flex items-center justify-end space-x-3 pt-3 border-t border-[#E5E9E8]">
              <button
                type="button"
                onClick={() => setVerifyModalTest(null)}
                className="px-4 py-2 bg-[#FFFFFF] hover:bg-[#F7F8FA] text-[#202A32] border border-[#E5E9E8] rounded-md text-xs font-medium cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleLaunchVerification}
                disabled={verifying}
                className="inline-flex items-center space-x-1.5 px-4 py-2 bg-[#0F766E] hover:bg-[#0D6860] text-white rounded-md text-xs font-semibold shadow-sm transition-colors disabled:opacity-50 cursor-pointer"
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
