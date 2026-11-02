import React, { useEffect, useState } from 'react';
import { FolderGit2, Play, CheckCircle2, AlertTriangle, Layers, ShieldCheck, Activity } from 'lucide-react';
import { EmptyState } from '../components/EmptyState';
import { projectsApi, runsApi } from '../services/api';
import { Project, TestRun } from '../types';

interface DashboardProps {
  onNavigateToNew: () => void;
}

export const Dashboard: React.FC<DashboardProps> = ({ onNavigateToNew }) => {
  const [projects, setProjects] = useState<Project[]>([]);
  const [runs, setRuns] = useState<TestRun[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [projList, runList] = await Promise.all([
          projectsApi.list(),
          runsApi.list(),
        ]);
        setProjects(projList);
        setRuns(runList);
      } catch {
        // Retain empty state on initial startup or error
        setProjects([]);
        setRuns([]);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  const totalPassing = runs.reduce((acc, r) => acc + (r.consistently_passing_count || 0), 0);
  const totalFlaky = runs.reduce((acc, r) => acc + (r.flaky_tests_count || 0), 0);

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'COMPLETED':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium bg-[#EBF8F2] text-[#159B67] border border-[#A7E7CB]">
            Completed
          </span>
        );
      case 'RUNNING':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium bg-[#F0FDFA] text-[#0F766E] border border-[#CCFBF1]">
            <Activity className="w-3 h-3 mr-1 animate-spin" />
            Running
          </span>
        );
      case 'FAILED':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium bg-[#FDF2F2] text-[#DC4B4B] border border-[#F7BEBE]">
            Failed
          </span>
        );
      case 'CANCELLED':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium bg-[#FEF8EC] text-[#D99A22] border border-[#FADDA8]">
            Cancelled
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium bg-[#F1F3F7] text-[#647084] border border-[#E5E9E8]">
            {status}
          </span>
        );
    }
  };

  return (
    <div className="space-y-5">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-4 border-b border-[#E5E9E8]">
        <div>
          <h1 className="text-xl font-bold text-[#202A32] tracking-tight">System Overview</h1>
          <p className="text-xs text-[#647084] mt-0.5">
            Diagnostic metrics across registered projects and test execution sessions.
          </p>
        </div>
        <button
          onClick={onNavigateToNew}
          className="inline-flex items-center space-x-1.5 px-3.5 py-1.5 bg-[#0F766E] hover:bg-[#0D6860] text-white rounded-md font-medium text-xs transition-colors shadow-sm self-start sm:self-auto cursor-pointer"
        >
          <Play className="w-3.5 h-3.5 fill-white" />
          <span>New Analysis</span>
        </button>
      </div>

      {/* Metric Counters */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5">
        <div className="p-4 rounded-lg bg-[#FFFFFF] border border-[#E5E9E8] shadow-card hover:border-[#CBD5E1] transition-all">
          <div className="flex items-center justify-between text-[#647084] text-[11px] font-semibold uppercase tracking-wider mb-2">
            <span>Registered Projects</span>
            <div className="w-7 h-7 rounded bg-[#F0FDFA] border border-[#CCFBF1] flex items-center justify-center text-[#0F766E]">
              <FolderGit2 className="w-3.5 h-3.5" />
            </div>
          </div>
          <div className="text-2xl font-bold text-[#202A32] tabular-nums tracking-tight">
            {projects.length}
          </div>
          <div className="text-[11px] text-[#647084] mt-1">Ingested codebases</div>
        </div>

        <div className="p-4 rounded-lg bg-[#FFFFFF] border border-[#E5E9E8] shadow-card hover:border-[#CBD5E1] transition-all">
          <div className="flex items-center justify-between text-[#647084] text-[11px] font-semibold uppercase tracking-wider mb-2">
            <span>Execution Sessions</span>
            <div className="w-7 h-7 rounded bg-[#F1F3F7] border border-[#E5E9E8] flex items-center justify-center text-[#647084]">
              <Layers className="w-3.5 h-3.5" />
            </div>
          </div>
          <div className="text-2xl font-bold text-[#202A32] tabular-nums tracking-tight">
            {runs.length}
          </div>
          <div className="text-[11px] text-[#647084] mt-1">Total N-iteration runs</div>
        </div>

        <div className="p-4 rounded-lg bg-[#FFFFFF] border border-[#E5E9E8] shadow-card hover:border-[#CBD5E1] transition-all">
          <div className="flex items-center justify-between text-[#647084] text-[11px] font-semibold uppercase tracking-wider mb-2">
            <span>Deterministic Passes</span>
            <div className="w-7 h-7 rounded bg-[#EBF8F2] border border-[#A7E7CB] flex items-center justify-center text-[#159B67]">
              <CheckCircle2 className="w-3.5 h-3.5" />
            </div>
          </div>
          <div className="text-2xl font-bold text-[#202A32] tabular-nums tracking-tight">
            {totalPassing}
          </div>
          <div className="text-[11px] text-[#647084] mt-1">Stable (100% pass rate)</div>
        </div>

        <div className="p-4 rounded-lg bg-[#FFFFFF] border border-[#E5E9E8] shadow-card hover:border-[#CBD5E1] transition-all">
          <div className="flex items-center justify-between text-[#647084] text-[11px] font-semibold uppercase tracking-wider mb-2">
            <span>Flaky Tests Detected</span>
            <div className="w-7 h-7 rounded bg-[#FEF8EC] border border-[#FADDA8] flex items-center justify-center text-[#D99A22]">
              <AlertTriangle className="w-3.5 h-3.5" />
            </div>
          </div>
          <div className="text-2xl font-bold text-[#202A32] tabular-nums tracking-tight">
            {totalFlaky}
          </div>
          <div className="text-[11px] text-[#647084] mt-1">Intermittent test outcomes</div>
        </div>
      </div>

      {/* Main Content Area */}
      <div className="bg-[#FFFFFF] border border-[#E5E9E8] rounded-lg shadow-card p-5">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-sm font-semibold text-[#202A32]">Recent Execution Sessions</h2>
            <p className="text-xs text-[#647084]">
              Session history and outcome classifications across completed runs.
            </p>
          </div>
          {runs.length > 0 && (
            <span className="text-[11px] text-[#647084] tabular-nums font-mono">
              {runs.length} {runs.length === 1 ? 'session' : 'sessions'}
            </span>
          )}
        </div>

        {loading ? (
          <div className="py-12 text-center text-xs text-[#647084]">Loading session telemetry...</div>
        ) : runs.length === 0 ? (
          <EmptyState
            icon={Layers}
            title="No Test Runs Recorded"
            description="No test suites have been executed yet. Upload a project to execute repeated isolated runs and detect flaky tests."
            actionLabel="Start New Analysis"
            onAction={onNavigateToNew}
          />
        ) : (
          <div className="overflow-x-auto border border-[#E5E9E8] rounded-md">
            <table className="w-full text-left text-xs text-[#202A32]">
              <thead className="text-[11px] uppercase bg-[#F7F8FA] text-[#647084] border-b border-[#E5E9E8]">
                <tr>
                  <th className="px-3.5 py-2.5 font-semibold">Run ID</th>
                  <th className="px-3.5 py-2.5 font-semibold">Status</th>
                  <th className="px-3.5 py-2.5 font-semibold">Iterations</th>
                  <th className="px-3.5 py-2.5 font-semibold">Total Tests</th>
                  <th className="px-3.5 py-2.5 font-semibold">Passing</th>
                  <th className="px-3.5 py-2.5 font-semibold">Failing</th>
                  <th className="px-3.5 py-2.5 font-semibold">Flaky</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#E5E9E8] bg-[#FFFFFF]">
                {runs.map((run) => (
                  <tr key={run.id} className="hover:bg-[#F7F8FA] transition-colors">
                    <td className="px-3.5 py-2.5 font-mono text-xs text-[#0F766E] font-medium">
                      {run.id.slice(0, 8)}...
                    </td>
                    <td className="px-3.5 py-2.5">{getStatusBadge(run.status)}</td>
                    <td className="px-3.5 py-2.5 font-mono tabular-nums text-[#647084]">
                      {run.iteration_count}
                    </td>
                    <td className="px-3.5 py-2.5 font-mono tabular-nums text-[#202A32] font-medium">
                      {run.total_tests}
                    </td>
                    <td className="px-3.5 py-2.5 font-mono tabular-nums text-[#159B67] font-medium">
                      {run.consistently_passing_count}
                    </td>
                    <td className="px-3.5 py-2.5 font-mono tabular-nums text-[#DC4B4B] font-medium">
                      {run.consistently_failing_count}
                    </td>
                    <td className="px-3.5 py-2.5 font-mono tabular-nums text-[#D99A22] font-semibold">
                      {run.flaky_tests_count}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Architecture Notice Banner */}
      <div className="p-3.5 rounded-lg bg-[#FFFFFF] border border-[#E5E9E8] shadow-card flex items-start space-x-3 text-xs text-[#647084]">
        <ShieldCheck className="w-4 h-4 text-[#14B8A6] shrink-0 mt-0.5" />
        <div>
          <span className="font-semibold text-[#202A32]">FLAKELENS Engine: </span>
          Phase 3 diagnostic architecture is fully active with containerized multi-iteration execution, flakiness scoring, root cause analysis, and fix verification.
        </div>
      </div>
    </div>
  );
};
