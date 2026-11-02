import React, { useState, useEffect } from 'react';
import {
  GitCompare,
  Terminal,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Layers,
  TrendingUp,
} from 'lucide-react';
import { EmptyState } from '../components/EmptyState';
import { projectsApi, runsApi, reportsApi } from '../services/api';
import {
  Project,
  TestRun,
  RunComparisonResponse,
  TestTransition,
  IterationDiffResponse,
  FlakinessReport,
} from '../types';

interface DiffInspectorProps {
  initialRunAId?: string;
  initialRunBId?: string;
}

export const DiffInspector: React.FC<DiffInspectorProps> = ({
  initialRunAId,
  initialRunBId,
}) => {
  const [activeSubTab, setActiveSubTab] = useState<'run-compare' | 'iteration-diff'>('run-compare');

  // Common State
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string>('');
  const [projectRuns, setProjectRuns] = useState<TestRun[]>([]);

  // Sub-Tab 1: Run-to-Run Compare State
  const [runAId, setRunAId] = useState<string>(initialRunAId || '');
  const [runBId, setRunBId] = useState<string>(initialRunBId || '');
  const [comparison, setComparison] = useState<RunComparisonResponse | null>(null);
  const [compareLoading, setCompareLoading] = useState<boolean>(false);
  const [compareError, setCompareError] = useState<string | null>(null);
  const [transitionFilter, setTransitionFilter] = useState<string>('ALL');

  // Sub-Tab 2: Iteration Log Diff State
  const [selectedDiffRunId, setSelectedDiffRunId] = useState<string>('');
  const [diffReports, setDiffReports] = useState<FlakinessReport[]>([]);
  const [selectedTestCaseId, setSelectedTestCaseId] = useState<string>('');
  const [iterationDiff, setIterationDiff] = useState<IterationDiffResponse | null>(null);
  const [diffLoading, setDiffLoading] = useState<boolean>(false);
  const [diffError, setDiffError] = useState<string | null>(null);

  // Load Projects on Mount
  useEffect(() => {
    const fetchProjects = async () => {
      try {
        const list = await projectsApi.list();
        setProjects(list);
        if (list.length > 0) {
          setSelectedProjectId(list[0].id);
        }
      } catch {
        setProjects([]);
      }
    };
    fetchProjects();
  }, []);

  // When selected project changes, fetch its runs
  useEffect(() => {
    if (!selectedProjectId) {
      setProjectRuns([]);
      return;
    }

    const fetchRuns = async () => {
      try {
        const list = await runsApi.list({ project_id: selectedProjectId });
        setProjectRuns(list);

        const completedRuns = list.filter((r) => r.status === 'COMPLETED' || r.status === 'CANCELLED');
        if (completedRuns.length >= 2) {
          if (!runAId) setRunAId(completedRuns[1].id);
          if (!runBId) setRunBId(completedRuns[0].id);
        } else if (completedRuns.length === 1) {
          if (!runAId) setRunAId(completedRuns[0].id);
        }

        if (completedRuns.length > 0) {
          setSelectedDiffRunId(completedRuns[0].id);
        }
      } catch {
        setProjectRuns([]);
      }
    };
    fetchRuns();
  }, [selectedProjectId]);

  // Execute Run Comparison
  const handleExecuteComparison = async () => {
    if (!runAId || !runBId) return;
    setCompareLoading(true);
    setCompareError(null);
    try {
      const result = await runsApi.compare(runAId, runBId);
      setComparison(result);
    } catch (err: any) {
      setCompareError(err?.response?.data?.detail || err?.message || 'Comparison failed.');
      setComparison(null);
    } finally {
      setCompareLoading(false);
    }
  };

  useEffect(() => {
    if (runAId && runBId && runAId !== runBId) {
      handleExecuteComparison();
    }
  }, [runAId, runBId]);

  // When selectedDiffRunId changes, fetch its flaky reports
  useEffect(() => {
    if (!selectedDiffRunId) {
      setDiffReports([]);
      return;
    }
    const fetchReports = async () => {
      try {
        const reps = await reportsApi.getByRun(selectedDiffRunId);
        setDiffReports(reps);
        const flakyOrFailing = reps.filter(
          (r) => r.outcome_classification === 'FLAKY' || r.outcome_classification === 'CONSISTENTLY_FAILING'
        );
        if (flakyOrFailing.length > 0) {
          setSelectedTestCaseId(flakyOrFailing[0].test_case_id);
        } else if (reps.length > 0) {
          setSelectedTestCaseId(reps[0].test_case_id);
        }
      } catch {
        setDiffReports([]);
      }
    };
    fetchReports();
  }, [selectedDiffRunId]);

  // Fetch Iteration Diff for selected test case
  useEffect(() => {
    if (!selectedDiffRunId || !selectedTestCaseId) {
      setIterationDiff(null);
      return;
    }
    const fetchDiff = async () => {
      setDiffLoading(true);
      setDiffError(null);
      try {
        const diff = await reportsApi.getDiff(selectedDiffRunId, selectedTestCaseId);
        setIterationDiff(diff);
      } catch (err: any) {
        setDiffError(err?.response?.data?.detail || 'Failed to load iteration diff.');
        setIterationDiff(null);
      } finally {
        setDiffLoading(false);
      }
    };
    fetchDiff();
  }, [selectedDiffRunId, selectedTestCaseId]);

  const getTransitionBadge = (transition: TestTransition) => {
    switch (transition) {
      case 'RECOVERED':
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-0.5 rounded text-[11px] font-medium bg-[#EBF8F2] text-[#159B67] border border-[#A7E7CB]">
            <CheckCircle2 className="w-3 h-3" />
            <span>Recovered / Fixed</span>
          </span>
        );
      case 'NEWLY_FAILING':
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-0.5 rounded text-[11px] font-medium bg-[#FDF2F2] text-[#DC4B4B] border border-[#F7BEBE]">
            <XCircle className="w-3 h-3" />
            <span>Newly Failing (Regression)</span>
          </span>
        );
      case 'NEWLY_FLAKY':
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-0.5 rounded text-[11px] font-medium bg-[#FEF8EC] text-[#D99A22] border border-[#FADDA8]">
            <AlertTriangle className="w-3 h-3" />
            <span>Newly Flaky</span>
          </span>
        );
      case 'STILL_FLAKY':
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-0.5 rounded text-[11px] font-medium bg-[#FEF8EC] text-[#D99A22] border border-[#FADDA8]">
            <TrendingUp className="w-3 h-3" />
            <span>Still Flaky</span>
          </span>
        );
      case 'STILL_FAILING':
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-0.5 rounded text-[11px] font-medium bg-[#FDF2F2] text-[#DC4B4B] border border-[#F7BEBE]">
            <XCircle className="w-3 h-3" />
            <span>Still Failing</span>
          </span>
        );
      case 'UNCHANGED_PASSING':
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-0.5 rounded text-[11px] font-medium bg-[#F1F3F7] text-[#647084] border border-[#E5E9E8]">
            <span>Stable Pass</span>
          </span>
        );
      case 'ADDED':
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-0.5 rounded text-[11px] font-medium bg-[#F0FDFA] text-[#0F766E] border border-[#CCFBF1]">
            <span>Added Test</span>
          </span>
        );
      case 'REMOVED':
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-0.5 rounded text-[11px] font-medium bg-[#F1F3F7] text-[#647084] border border-[#E5E9E8]">
            <span>Removed Test</span>
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-0.5 rounded text-[11px] font-medium bg-[#F1F3F7] text-[#8993A2] border border-[#E5E9E8]">
            <span>Inconclusive</span>
          </span>
        );
    }
  };

  const filteredComparisons = (comparison?.test_comparisons || []).filter((item) => {
    if (transitionFilter === 'ALL') return true;
    return item.transition === transitionFilter;
  });

  return (
    <div className="space-y-5">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-4 border-b border-[#E5E9E8]">
        <div>
          <h1 className="text-xl font-bold text-[#202A32] tracking-tight">Execution Comparisons &amp; Diffs</h1>
          <p className="text-xs text-[#647084] mt-0.5">
            Compare two historical runs of the same project to track regressions and recoveries, or inspect side-by-side iteration console diffs.
          </p>
        </div>

        {/* Sub-Tab Switcher */}
        <div className="flex bg-[#F1F5F5] border border-[#E5E9E8] rounded-md p-1 space-x-1 self-start sm:self-auto">
          <button
            onClick={() => setActiveSubTab('run-compare')}
            className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors cursor-pointer ${
              activeSubTab === 'run-compare'
                ? 'bg-[#FFFFFF] text-[#202A32] border border-[#E5E9E8] shadow-sm'
                : 'text-[#647084] hover:text-[#202A32]'
            }`}
          >
            Run vs. Run Comparison
          </button>
          <button
            onClick={() => setActiveSubTab('iteration-diff')}
            className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors cursor-pointer ${
              activeSubTab === 'iteration-diff'
                ? 'bg-[#FFFFFF] text-[#202A32] border border-[#E5E9E8] shadow-sm'
                : 'text-[#647084] hover:text-[#202A32]'
            }`}
          >
            Iteration Log Diff
          </button>
        </div>
      </div>

      {/* VIEW 1: RUN VS RUN COMPARISON */}
      {activeSubTab === 'run-compare' && (
        <div className="space-y-5">
          {/* Run Selection Panel */}
          <div className="bg-[#FFFFFF] border border-[#E5E9E8] rounded-lg p-4 sm:p-5 space-y-4 shadow-card">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {/* Project Dropdown */}
              <div>
                <label className="block text-xs font-medium text-[#647084] uppercase tracking-wider mb-1">
                  Target Project
                </label>
                <select
                  value={selectedProjectId}
                  onChange={(e) => setSelectedProjectId(e.target.value)}
                  className="w-full bg-[#FFFFFF] border border-[#E5E9E8] rounded-md px-3 py-2 text-sm text-[#202A32] focus:outline-none focus:ring-1 focus:ring-[#0F766E] focus:border-[#0F766E]"
                >
                  {projects.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </div>

              {/* Baseline Run (Run A) */}
              <div>
                <label className="block text-xs font-medium text-[#647084] uppercase tracking-wider mb-1">
                  Baseline Run (Run A)
                </label>
                <select
                  value={runAId}
                  onChange={(e) => setRunAId(e.target.value)}
                  className="w-full bg-[#FFFFFF] border border-[#E5E9E8] rounded-md px-3 py-2 text-sm text-[#202A32] focus:outline-none focus:ring-1 focus:ring-[#0F766E] focus:border-[#0F766E]"
                >
                  <option value="">Select Baseline Run</option>
                  {projectRuns.map((r, idx) => (
                    <option key={r.id} value={r.id} disabled={r.id === runBId}>
                      Run #{projectRuns.length - idx} ({r.status}) - {r.id.slice(0, 8)}
                    </option>
                  ))}
                </select>
              </div>

              {/* Comparison Run (Run B) */}
              <div>
                <label className="block text-xs font-medium text-[#647084] uppercase tracking-wider mb-1">
                  Comparison Run (Run B)
                </label>
                <select
                  value={runBId}
                  onChange={(e) => setRunBId(e.target.value)}
                  className="w-full bg-[#FFFFFF] border border-[#E5E9E8] rounded-md px-3 py-2 text-sm text-[#202A32] focus:outline-none focus:ring-1 focus:ring-[#0F766E] focus:border-[#0F766E]"
                >
                  <option value="">Select Comparison Run</option>
                  {projectRuns.map((r, idx) => (
                    <option key={r.id} value={r.id} disabled={r.id === runAId}>
                      Run #{projectRuns.length - idx} ({r.status}) - {r.id.slice(0, 8)}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          {/* Comparison Output */}
          {compareLoading ? (
            <div className="bg-[#FFFFFF] border border-[#E5E9E8] rounded-lg p-12 text-center text-[#647084] text-sm">
              <Layers className="w-6 h-6 animate-spin mx-auto mb-2 text-[#0F766E]" />
              Computing multi-run delta &amp; transition matrix...
            </div>
          ) : compareError ? (
            <div className="p-4 bg-[#FDF2F2] border border-[#F7BEBE] rounded-lg text-[#DC4B4B] text-sm flex items-center justify-between">
              <span>{compareError}</span>
              <button
                onClick={handleExecuteComparison}
                className="px-3 py-1 bg-[#FDF2F2] hover:bg-[#F7BEBE] text-[#DC4B4B] border border-[#F7BEBE] rounded text-xs font-medium cursor-pointer"
              >
                Retry
              </button>
            </div>
          ) : !comparison ? (
            <div className="bg-[#FFFFFF] border border-[#E5E9E8] rounded-lg p-6">
              <EmptyState
                icon={GitCompare}
                title="Select Two Runs to Compare"
                description="Choose an earlier baseline run and a later comparison run from the dropdowns above to inspect test recoveries, new regressions, and duration variances."
              />
            </div>
          ) : (
            <div className="space-y-4">
              {/* Summary Delta Banner */}
              <div className="grid grid-cols-2 sm:grid-cols-6 gap-3">
                <div className="p-3 bg-[#EBF8F2] border border-[#A7E7CB] rounded-lg">
                  <div className="text-[10px] uppercase tracking-wider text-[#159B67] font-medium">
                    Recovered / Fixed
                  </div>
                  <div className="text-xl font-bold text-[#159B67] mt-1">
                    +{comparison.summary_delta.recovered_count}
                  </div>
                </div>

                <div className="p-3 bg-[#FDF2F2] border border-[#F7BEBE] rounded-lg">
                  <div className="text-[10px] uppercase tracking-wider text-[#DC4B4B] font-medium">
                    Newly Failing
                  </div>
                  <div className="text-xl font-bold text-[#DC4B4B] mt-1">
                    +{comparison.summary_delta.newly_failing_count}
                  </div>
                </div>

                <div className="p-3 bg-[#FEF8EC] border border-[#FADDA8] rounded-lg">
                  <div className="text-[10px] uppercase tracking-wider text-[#D99A22] font-medium">
                    Newly Flaky
                  </div>
                  <div className="text-xl font-bold text-[#D99A22] mt-1">
                    +{comparison.summary_delta.newly_flaky_count}
                  </div>
                </div>

                <div className="p-3 bg-[#FEF8EC] border border-[#FADDA8] rounded-lg">
                  <div className="text-[10px] uppercase tracking-wider text-[#D99A22] font-medium">
                    Still Flaky
                  </div>
                  <div className="text-xl font-bold text-[#D99A22] mt-1">
                    {comparison.summary_delta.still_flaky_count}
                  </div>
                </div>

                <div className="p-3 bg-[#F7F8FA] border border-[#E5E9E8] rounded-lg">
                  <div className="text-[10px] uppercase tracking-wider text-[#647084] font-medium">
                    Net Flaky Delta
                  </div>
                  <div
                    className={`text-xl font-bold mt-1 ${
                      comparison.summary_delta.flaky_count_delta < 0
                        ? 'text-[#159B67]'
                        : comparison.summary_delta.flaky_count_delta > 0
                        ? 'text-[#DC4B4B]'
                        : 'text-[#202A32]'
                    }`}
                  >
                    {comparison.summary_delta.flaky_count_delta > 0 ? '+' : ''}
                    {comparison.summary_delta.flaky_count_delta}
                  </div>
                </div>

                <div className="p-3 bg-[#F7F8FA] border border-[#E5E9E8] rounded-lg">
                  <div className="text-[10px] uppercase tracking-wider text-[#647084] font-medium">
                    Stable Pass
                  </div>
                  <div className="text-xl font-bold text-[#202A32] mt-1">
                    {comparison.summary_delta.unchanged_passing_count}
                  </div>
                </div>
              </div>

              {/* Transition Filter Pills */}
              <div className="flex flex-wrap gap-2 pt-1">
                {['ALL', 'RECOVERED', 'NEWLY_FAILING', 'NEWLY_FLAKY', 'STILL_FLAKY', 'STILL_FAILING'].map((cat) => (
                  <button
                    key={cat}
                    onClick={() => setTransitionFilter(cat)}
                    className={`px-3 py-1 rounded-md text-xs font-medium transition-colors cursor-pointer ${
                      transitionFilter === cat
                        ? 'bg-[#0F766E] text-white'
                        : 'bg-[#F7F8FA] text-[#647084] hover:bg-[#F1F5F5] border border-[#E5E9E8]'
                    }`}
                  >
                    {cat.replace('_', ' ')}
                  </button>
                ))}
              </div>

              {/* Comparisons Table */}
              <div className="bg-[#FFFFFF] border border-[#E5E9E8] rounded-lg overflow-hidden shadow-card">
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs text-[#202A32]">
                    <thead className="text-[11px] uppercase bg-[#F7F8FA] text-[#647084] border-b border-[#E5E9E8]">
                      <tr>
                        <th className="px-3.5 py-2.5 font-semibold">Test Case</th>
                        <th className="px-3.5 py-2.5 font-semibold">Transition Verdict</th>
                        <th className="px-3.5 py-2.5 font-semibold">Run A (Baseline)</th>
                        <th className="px-3.5 py-2.5 font-semibold">Run B (Comparison)</th>
                        <th className="px-3.5 py-2.5 font-semibold">Flakiness Δ</th>
                        <th className="px-3.5 py-2.5 font-semibold">Duration Δ</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#E5E9E8] bg-[#FFFFFF]">
                      {filteredComparisons.map((item) => (
                        <tr key={item.test_case_id} className="hover:bg-[#F7F8FA] transition-colors">
                          <td className="px-3.5 py-2.5 font-mono">
                            <div className="font-semibold text-[#202A32] truncate max-w-xs sm:max-w-md">
                              {item.node_id}
                            </div>
                            <div className="text-[11px] text-[#8993A2] truncate">{item.file_path}</div>
                          </td>
                          <td className="px-3.5 py-2.5 whitespace-nowrap">
                            {getTransitionBadge(item.transition as TestTransition)}
                          </td>
                          <td className="px-3.5 py-2.5 whitespace-nowrap font-mono text-[#202A32]">
                            {item.status_a ? (
                              <div>
                                <span className="font-semibold">{item.status_a}</span>
                                {item.flakiness_score_a !== null && item.flakiness_score_a !== undefined && (
                                  <span className="text-[#647084] block text-[11px]">
                                    F={item.flakiness_score_a.toFixed(4)}
                                  </span>
                                )}
                              </div>
                            ) : (
                              <span className="text-[#8993A2] italic">Not Executed</span>
                            )}
                          </td>
                          <td className="px-3.5 py-2.5 whitespace-nowrap font-mono text-[#202A32]">
                            {item.status_b ? (
                              <div>
                                <span className="font-semibold">{item.status_b}</span>
                                {item.flakiness_score_b !== null && item.flakiness_score_b !== undefined && (
                                  <span className="text-[#647084] block text-[11px]">
                                    F={item.flakiness_score_b.toFixed(4)}
                                  </span>
                                )}
                              </div>
                            ) : (
                              <span className="text-[#8993A2] italic">Not Executed</span>
                            )}
                          </td>
                          <td className="px-3.5 py-2.5 whitespace-nowrap font-mono">
                            {item.flakiness_score_delta !== null && item.flakiness_score_delta !== undefined ? (
                              <span
                                className={`font-semibold ${
                                  item.flakiness_score_delta < 0
                                    ? 'text-[#159B67]'
                                    : item.flakiness_score_delta > 0
                                    ? 'text-[#DC4B4B]'
                                    : 'text-[#647084]'
                                }`}
                              >
                                {item.flakiness_score_delta > 0 ? '+' : ''}
                                {item.flakiness_score_delta.toFixed(4)}
                              </span>
                            ) : (
                              <span className="text-[#8993A2]">-</span>
                            )}
                          </td>
                          <td className="px-3.5 py-2.5 whitespace-nowrap font-mono text-[#647084]">
                            {item.duration_delta_ms !== null && item.duration_delta_ms !== undefined ? (
                              <span>
                                {item.duration_delta_ms > 0 ? '+' : ''}
                                {item.duration_delta_ms} ms
                              </span>
                            ) : (
                              <span className="text-[#8993A2]">-</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* VIEW 2: ITERATION LOG DIFF */}
      {activeSubTab === 'iteration-diff' && (
        <div className="space-y-5">
          {/* Controls */}
          <div className="bg-[#FFFFFF] border border-[#E5E9E8] rounded-lg p-4 sm:p-5 shadow-card">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-[#647084] uppercase tracking-wider mb-1">
                  Target Run
                </label>
                <select
                  value={selectedDiffRunId}
                  onChange={(e) => setSelectedDiffRunId(e.target.value)}
                  className="w-full bg-[#FFFFFF] border border-[#E5E9E8] rounded-md px-3 py-2 text-sm text-[#202A32] focus:outline-none focus:ring-1 focus:ring-[#0F766E] focus:border-[#0F766E]"
                >
                  {projectRuns.map((r, idx) => (
                    <option key={r.id} value={r.id}>
                      Run #{projectRuns.length - idx} ({r.status}) - {r.id.slice(0, 8)}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-[#647084] uppercase tracking-wider mb-1">
                  Target Test Case
                </label>
                <select
                  value={selectedTestCaseId}
                  onChange={(e) => setSelectedTestCaseId(e.target.value)}
                  className="w-full bg-[#FFFFFF] border border-[#E5E9E8] rounded-md px-3 py-2 text-sm text-[#202A32] focus:outline-none focus:ring-1 focus:ring-[#0F766E] focus:border-[#0F766E]"
                >
                  {diffReports.map((rep) => (
                    <option key={rep.test_case_id} value={rep.test_case_id}>
                      [{rep.outcome_classification}] {rep.node_id || rep.test_name}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          {/* Diff Output */}
          {diffLoading ? (
            <div className="bg-[#FFFFFF] border border-[#E5E9E8] rounded-lg p-12 text-center text-[#647084] text-sm">
              <Layers className="w-6 h-6 animate-spin mx-auto mb-2 text-[#0F766E]" />
              Computing unified iteration diff...
            </div>
          ) : diffError ? (
            <div className="p-4 bg-[#FDF2F2] border border-[#F7BEBE] rounded-lg text-[#DC4B4B] text-sm">
              {diffError}
            </div>
          ) : !iterationDiff ? (
            <div className="bg-[#FFFFFF] border border-[#E5E9E8] rounded-lg p-6">
              <EmptyState
                icon={Terminal}
                title="No Intermittent Diffs to Inspect"
                description="Select a flaky test case that contains both passing and failing executions to compute side-by-side console and traceback diffs."
              />
            </div>
          ) : (
            <div className="space-y-4">
              {/* Duration Delta Banner */}
              <div className="bg-[#FFFFFF] border border-[#E5E9E8] rounded-lg shadow-card p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div className="font-mono text-xs">
                  <span className="text-[#647084]">Inspecting: </span>
                  <span className="font-bold text-[#202A32]">{iterationDiff.node_id}</span>
                </div>
                {iterationDiff.duration_delta_ms !== null && (
                  <div className="flex items-center space-x-2 text-xs font-mono">
                    <span className="text-[#647084]">Duration Delta (Fail vs Pass):</span>
                    <span
                      className={`font-bold ${
                        (iterationDiff.duration_delta_ms ?? 0) > 0 ? 'text-[#D99A22]' : 'text-[#159B67]'
                      }`}
                    >
                      {(iterationDiff.duration_delta_ms ?? 0) > 0 ? '+' : ''}
                      {iterationDiff.duration_delta_ms} ms
                    </span>
                  </div>
                )}
              </div>

              {/* Unified Diff Viewers */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Passing Iteration Box */}
                <div className="bg-[#FFFFFF] border border-[#E5E9E8] rounded-lg p-4 space-y-2 shadow-card">
                  <div className="flex items-center space-x-2 text-[#159B67] font-semibold text-xs uppercase tracking-wider">
                    <CheckCircle2 className="w-4 h-4" />
                    <span>
                      Passing Iteration #{iterationDiff.passing_iteration?.iteration_number ?? 'N/A'} (
                      {iterationDiff.passing_iteration?.duration_ms.toFixed(1)} ms)
                    </span>
                  </div>
                  <pre className="p-3 rounded-md bg-[#F1F3F7] border border-[#E5E9E8] text-[#202A32] text-xs font-mono whitespace-pre-wrap max-h-72 overflow-y-auto">
                    {iterationDiff.passing_iteration?.stdout || 'No stdout output captured.'}
                  </pre>
                </div>

                {/* Failing Iteration Box */}
                <div className="bg-[#FFFFFF] border border-[#E5E9E8] rounded-lg p-4 space-y-2 shadow-card">
                  <div className="flex items-center space-x-2 text-[#DC4B4B] font-semibold text-xs uppercase tracking-wider">
                    <XCircle className="w-4 h-4" />
                    <span>
                      Failing Iteration #{iterationDiff.failing_iteration?.iteration_number ?? 'N/A'} (
                      {iterationDiff.failing_iteration?.duration_ms.toFixed(1)} ms)
                    </span>
                  </div>
                  <pre className="p-3 rounded-md bg-[#FDF2F2] border border-[#F7BEBE] text-[#DC4B4B] text-xs font-mono whitespace-pre-wrap max-h-72 overflow-y-auto">
                    {iterationDiff.failing_iteration?.traceback ||
                      iterationDiff.failing_iteration?.error_message ||
                      'No error traceback captured.'}
                  </pre>
                </div>
              </div>

              {/* Unified Line Diff */}
              {iterationDiff.stderr_diff && (
                <div className="bg-[#FFFFFF] border border-[#E5E9E8] rounded-lg shadow-card p-4 space-y-2 font-mono text-xs">
                  <div className="text-[#202A32] font-semibold">Unified Console / Stderr Delta</div>
                  <pre className="p-3 rounded-md bg-[#F1F3F7] border border-[#E5E9E8] text-[#202A32] font-mono text-[11px] overflow-x-auto whitespace-pre max-h-60 overflow-y-auto">
                    {iterationDiff.stderr_diff}
                  </pre>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
