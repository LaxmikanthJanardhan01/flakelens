import React, { useEffect, useState } from 'react';
import { FolderGit2, Play, CheckCircle2, XCircle, AlertTriangle, Layers } from 'lucide-react';
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
        // Backend empty or starting up; retain empty array
        setProjects([]);
        setRuns([]);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-4 border-b border-slate-800">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">System Overview</h1>
          <p className="text-sm text-slate-400 mt-1">
            Aggregated diagnostic metrics across registered projects and test execution sessions.
          </p>
        </div>
        <button
          onClick={onNavigateToNew}
          className="inline-flex items-center space-x-2 px-4 py-2 bg-sky-600 hover:bg-sky-500 text-white rounded-lg font-medium text-sm transition-colors shadow-sm self-start sm:self-auto"
        >
          <Play className="w-4 h-4 fill-white" />
          <span>New Analysis</span>
        </button>
      </div>

      {/* Real Metric Counters (Zero/Genuine State) */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="p-4 rounded-xl bg-slate-800/50 border border-slate-800">
          <div className="flex items-center justify-between text-slate-400 text-xs font-medium uppercase tracking-wider mb-2">
            <span>Registered Projects</span>
            <FolderGit2 className="w-4 h-4 text-sky-400" />
          </div>
          <div className="text-2xl font-bold text-white">{projects.length}</div>
          <div className="text-[11px] text-slate-400 mt-1">Ingested codebases</div>
        </div>

        <div className="p-4 rounded-xl bg-slate-800/50 border border-slate-800">
          <div className="flex items-center justify-between text-slate-400 text-xs font-medium uppercase tracking-wider mb-2">
            <span>Execution Sessions</span>
            <Layers className="w-4 h-4 text-indigo-400" />
          </div>
          <div className="text-2xl font-bold text-white">{runs.length}</div>
          <div className="text-[11px] text-slate-400 mt-1">Total N-iteration runs</div>
        </div>

        <div className="p-4 rounded-xl bg-slate-800/50 border border-slate-800">
          <div className="flex items-center justify-between text-slate-400 text-xs font-medium uppercase tracking-wider mb-2">
            <span>Deterministic Passes</span>
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="text-2xl font-bold text-white">
            {runs.reduce((acc, r) => acc + (r.consistently_passing_count || 0), 0)}
          </div>
          <div className="text-[11px] text-slate-400 mt-1">Stable (100% pass rate)</div>
        </div>

        <div className="p-4 rounded-xl bg-slate-800/50 border border-slate-800">
          <div className="flex items-center justify-between text-slate-400 text-xs font-medium uppercase tracking-wider mb-2">
            <span>Flaky Tests Detected</span>
            <AlertTriangle className="w-4 h-4 text-amber-400" />
          </div>
          <div className="text-2xl font-bold text-white">
            {runs.reduce((acc, r) => acc + (r.flaky_tests_count || 0), 0)}
          </div>
          <div className="text-[11px] text-slate-400 mt-1">Intermittent outcomes</div>
        </div>
      </div>

      {/* Main Content Area: Genuine Empty State */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
        <h2 className="text-base font-semibold text-white mb-2">Recent Execution Sessions</h2>
        <p className="text-xs text-slate-400 mb-4">
          Session history and aggregated outcome classifications.
        </p>

        {loading ? (
          <div className="py-12 text-center text-sm text-slate-400">Loading session telemetry...</div>
        ) : runs.length === 0 ? (
          <EmptyState
            icon={Layers}
            title="No Test Runs Recorded"
            description="No test suites have been executed yet. In Phase 2, uploaded projects will be executed repeatedly in isolated Docker sandboxes to detect non-deterministic test behavior."
            actionLabel="Start New Analysis"
            onAction={onNavigateToNew}
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-slate-300">
              <thead className="text-xs uppercase bg-slate-800 text-slate-400 border-b border-slate-700">
                <tr>
                  <th className="px-4 py-3">Run ID</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Iterations</th>
                  <th className="px-4 py-3">Total Tests</th>
                  <th className="px-4 py-3">Passing</th>
                  <th className="px-4 py-3">Failing</th>
                  <th className="px-4 py-3">Flaky</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {runs.map((run) => (
                  <tr key={run.id} className="hover:bg-slate-800/40">
                    <td className="px-4 py-3 font-mono text-xs text-sky-400">{run.id.slice(0, 8)}...</td>
                    <td className="px-4 py-3">
                      <span className="px-2 py-0.5 rounded text-xs bg-slate-800 text-slate-300 border border-slate-700">
                        {run.status}
                      </span>
                    </td>
                    <td className="px-4 py-3">{run.iteration_count}</td>
                    <td className="px-4 py-3">{run.total_tests}</td>
                    <td className="px-4 py-3 text-emerald-400">{run.consistently_passing_count}</td>
                    <td className="px-4 py-3 text-rose-400">{run.consistently_failing_count}</td>
                    <td className="px-4 py-3 text-amber-400 font-semibold">{run.flaky_tests_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Architectural Notice Card */}
      <div className="p-4 rounded-xl bg-slate-800/30 border border-slate-800 flex items-start space-x-3 text-xs text-slate-400">
        <XCircle className="w-4 h-4 text-slate-400 shrink-0 mt-0.5" />
        <div>
          <span className="font-semibold text-slate-300">Phase 1 Architecture Scaffold: </span>
          The SQLite database schema, FastAPI API endpoints, and React presentation components are active.
          Execution runner and container telemetry ingestion will be integrated in Phase 2.
        </div>
      </div>
    </div>
  );
};

