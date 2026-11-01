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
} from 'lucide-react';
import { EmptyState } from '../components/EmptyState';
import { runsApi, reportsApi } from '../services/api';
import { TestRun, FlakinessReport } from '../types';

interface ReportViewProps {
  onNavigateToNew: () => void;
}

export const ReportView: React.FC<ReportViewProps> = ({ onNavigateToNew }) => {
  const [runs, setRuns] = useState<TestRun[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string>('');
  const [reports, setReports] = useState<FlakinessReport[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [analyzing, setAnalyzing] = useState<boolean>(false);
  const [filter, setFilter] = useState<
    'ALL' | 'FLAKY' | 'FAILING' | 'PASSING' | 'INSUFFICIENT_DATA'
  >('ALL');

  useEffect(() => {
    const fetchRuns = async () => {
      try {
        setLoading(true);
        const runList = await runsApi.list();
        setRuns(runList);
        if (runList.length > 0) {
          // Default to the first (latest) run
          setSelectedRunId(runList[0].id);
        }
      } catch {
        setRuns([]);
      } finally {
        setLoading(false);
      }
    };
    fetchRuns();
  }, []);

  useEffect(() => {
    if (!selectedRunId) {
      setReports([]);
      return;
    }

    const fetchReports = async () => {
      try {
        setLoading(true);
        const data = await reportsApi.getByRun(selectedRunId);
        setReports(data);
      } catch {
        setReports([]);
      } finally {
        setLoading(false);
      }
    };

    fetchReports();
  }, [selectedRunId]);

  const handleAnalyze = async () => {
    if (!selectedRunId) return;
    try {
      setAnalyzing(true);
      const data = await reportsApi.analyze(selectedRunId);
      setReports(data);
      // Refresh run list to update summary counters
      const runList = await runsApi.list();
      setRuns(runList);
    } catch (err) {
      console.error('Failed to trigger analysis:', err);
    } finally {
      setAnalyzing(false);
    }
  };

  const selectedRun = runs.find((r) => r.id === selectedRunId);

  const filteredReports = reports.filter((r) => {
    if (filter === 'ALL') return true;
    return r.outcome_classification === filter;
  });

  const getClassificationBadge = (classification: FlakinessReport['outcome_classification']) => {
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

  return (
    <div className="space-y-6">
      {/* Header with Run Selector */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-4 border-b border-slate-800">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Root Cause Analysis & Flakiness Reports</h1>
          <p className="text-sm text-slate-400 mt-1">
            Tri-part outcome classification, flakiness score rankings, and evidence-based root cause diagnoses.
          </p>
        </div>

        {runs.length > 0 && (
          <div className="flex items-center space-x-3">
            <select
              value={selectedRunId}
              onChange={(e) => setSelectedRunId(e.target.value)}
              className="bg-slate-900 border border-slate-800 text-slate-200 text-xs rounded-lg px-3 py-2 focus:ring-1 focus:ring-sky-500 focus:outline-none"
            >
              {runs.map((r, idx) => (
                <option key={r.id} value={r.id}>
                  Run #{runs.length - idx} ({r.status}) - {r.iteration_count} iters - {r.id.slice(0, 8)}
                </option>
              ))}
            </select>

            <button
              onClick={handleAnalyze}
              disabled={analyzing || selectedRun?.status === 'RUNNING'}
              className="inline-flex items-center space-x-1.5 px-3 py-2 bg-slate-800 hover:bg-slate-700 disabled:opacity-50 text-slate-200 rounded-lg text-xs font-medium transition-colors border border-slate-700"
              title={selectedRun?.status === 'RUNNING' ? 'Cannot analyze while run is running' : 'Recompute flakiness analysis & RCA'}
            >
              <RefreshCw className={`w-3.5 h-3.5 ${analyzing ? 'animate-spin' : ''}`} />
              <span>{analyzing ? 'Analyzing...' : 'Analyze & Diagnose'}</span>
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
              : 'bg-slate-800/80 text-slate-400 hover:text-slate-200'
          }`}
        >
          <Filter className="w-3.5 h-3.5" />
          <span>All Outcomes ({reports.length})</span>
        </button>

        <button
          onClick={() => setFilter('FLAKY')}
          className={`flex items-center space-x-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
            filter === 'FLAKY'
              ? 'bg-amber-600 text-white'
              : 'bg-slate-800/80 text-amber-400 hover:bg-slate-800'
          }`}
        >
          <AlertTriangle className="w-3.5 h-3.5" />
          <span>
            Flaky ({reports.filter((r) => r.outcome_classification === 'FLAKY').length})
          </span>
        </button>

        <button
          onClick={() => setFilter('FAILING')}
          className={`flex items-center space-x-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
            filter === 'FAILING'
              ? 'bg-rose-600 text-white'
              : 'bg-slate-800/80 text-rose-400 hover:bg-slate-800'
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
          className={`flex items-center space-x-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
            filter === 'PASSING'
              ? 'bg-emerald-600 text-white'
              : 'bg-slate-800/80 text-emerald-400 hover:bg-slate-800'
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
          className={`flex items-center space-x-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
            filter === 'INSUFFICIENT_DATA'
              ? 'bg-slate-600 text-white'
              : 'bg-slate-800/80 text-slate-400 hover:bg-slate-800'
          }`}
        >
          <HelpCircle className="w-3.5 h-3.5" />
          <span>
            Insufficient Data (
            {reports.filter((r) => r.outcome_classification === 'INSUFFICIENT_DATA').length})
          </span>
        </button>
      </div>

      {/* Main Content Area */}
      {loading ? (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-12 text-center text-slate-400 text-sm">
          <Activity className="w-6 h-6 animate-spin mx-auto mb-2 text-sky-400" />
          Loading reports and root cause diagnoses...
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

            return (
              <div
                key={report.id}
                className="p-5 rounded-xl bg-slate-900 border border-slate-800 hover:border-slate-700 transition-colors space-y-4"
              >
                {/* Top Header: Node ID & Outcome Classification */}
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                  <div className="space-y-1">
                    <div className="font-mono text-sm font-semibold text-white break-all">
                      {report.node_id || report.test_name || `Test Case #${report.test_case_id.slice(0, 8)}`}
                    </div>
                    {report.file_path && (
                      <div className="text-xs text-slate-400 font-mono">
                        {report.file_path}
                      </div>
                    )}
                  </div>
                  <div>{getClassificationBadge(report.outcome_classification)}</div>
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
                        <span className="text-xs text-slate-500 font-mono">N/A (Deterministic Pass)</span>
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

                  {/* Suspected Preceding Tests (Execution Order Permutation Correlation) */}
                  {suspects.length > 0 && (
                    <div className="p-3 bg-purple-950/20 border border-purple-800/30 rounded-lg text-xs space-y-1.5">
                      <div className="flex items-center space-x-1.5 font-semibold text-purple-300">
                        <GitBranch className="w-3.5 h-3.5" />
                        <span>Suspected Preceding Tests (Permutation Correlation) ({suspects.length})</span>
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
                              {s.preceded_in_passes} passes) • Correlation: {(s.correlation_score * 100).toFixed(0)}% • Candidate Polluter
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

      {/* Classification Legend Card */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="p-4 rounded-xl bg-slate-800/30 border border-slate-800 space-y-1">
          <div className="flex items-center space-x-2 text-xs font-semibold text-emerald-400 uppercase tracking-wider">
            <CheckCircle2 className="w-4 h-4" />
            <span>Consistently Passing</span>
          </div>
          <div className="text-sm font-medium text-slate-200">Pass Rate = 100% (P = 1.0)</div>
          <p className="text-xs text-slate-400">
            Verified deterministic pass. Test is stable; no investigation required.
          </p>
        </div>

        <div className="p-4 rounded-xl bg-slate-800/30 border border-slate-800 space-y-1">
          <div className="flex items-center space-x-2 text-xs font-semibold text-rose-400 uppercase tracking-wider">
            <XCircle className="w-4 h-4" />
            <span>Consistently Failing</span>
          </div>
          <div className="text-sm font-medium text-slate-200">Fail Rate = 100% (F = 1.0)</div>
          <p className="text-xs text-slate-400">
            Deterministic bug. Not classified as stable; requires immediate code or assertion fix.
          </p>
        </div>

        <div className="p-4 rounded-xl bg-slate-800/30 border border-slate-800 space-y-1">
          <div className="flex items-center space-x-2 text-xs font-semibold text-amber-400 uppercase tracking-wider">
            <AlertTriangle className="w-4 h-4" />
            <span>Flaky (Intermittent)</span>
          </div>
          <div className="text-sm font-medium text-slate-200">0 &lt; Pass Rate &lt; 100%</div>
          <p className="text-xs text-slate-400">
            Non-deterministic outcome. Scored by flakiness formula and diagnosed by evidence-based RCA engine.
          </p>
        </div>
      </div>
    </div>
  );
};
