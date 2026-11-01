import React, { useEffect, useState } from 'react';
import {
  History,
  Search,
  ArrowUpDown,
  Play,
  FileBarChart2,
  GitCompare,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Clock,
  Layers,
  ShieldCheck,
  RotateCcw,
} from 'lucide-react';
import { EmptyState } from '../components/EmptyState';
import { projectsApi, runsApi } from '../services/api';
import { Project, TestRun } from '../types';

interface RunHistoryProps {
  onNavigateToReport: (runId: string) => void;
  onNavigateToCompare: (runAId: string, runBId?: string) => void;
  onNavigateToNew: () => void;
}

export const RunHistory: React.FC<RunHistoryProps> = ({
  onNavigateToReport,
  onNavigateToCompare,
  onNavigateToNew,
}) => {
  const [runs, setRuns] = useState<TestRun[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Filters & Search
  const [selectedProjectId, setSelectedProjectId] = useState<string>('all');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [typeFilter, setTypeFilter] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [sortBy, setSortBy] = useState<string>('started_at');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');

  const fetchRuns = async () => {
    setLoading(true);
    setError(null);
    try {
      const [projList, runList] = await Promise.all([
        projectsApi.list(),
        runsApi.list({
          project_id: selectedProjectId !== 'all' ? selectedProjectId : undefined,
          status: statusFilter !== 'all' ? statusFilter : undefined,
          run_type: typeFilter !== 'all' ? typeFilter : undefined,
          search: searchQuery.trim() || undefined,
          sort_by: sortBy,
          sort_order: sortOrder,
        }),
      ]);
      setProjects(projList);
      setRuns(runList);
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || 'Failed to load run history.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchRuns();
  }, [selectedProjectId, statusFilter, typeFilter, sortBy, sortOrder]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    fetchRuns();
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'COMPLETED':
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
            <CheckCircle2 className="w-3 h-3" />
            <span>Completed</span>
          </span>
        );
      case 'RUNNING':
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-sky-500/10 text-sky-400 border border-sky-500/30">
            <Layers className="w-3 h-3 animate-spin" />
            <span>Running</span>
          </span>
        );
      case 'FAILED':
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-rose-500/10 text-rose-400 border border-rose-500/30">
            <XCircle className="w-3 h-3" />
            <span>Failed</span>
          </span>
        );
      case 'CANCELLED':
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-500/10 text-amber-400 border border-amber-500/30">
            <AlertTriangle className="w-3 h-3" />
            <span>Cancelled</span>
          </span>
        );
      case 'TIMED_OUT':
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-red-500/10 text-red-400 border border-red-500/30">
            <Clock className="w-3 h-3" />
            <span>Timed Out</span>
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-700 text-slate-300">
            <span>{status}</span>
          </span>
        );
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-4 border-b border-slate-800">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight flex items-center space-x-2">
            <History className="w-6 h-6 text-sky-400" />
            <span>Project Run History</span>
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Historical execution sessions across projects with search, multi-factor filtering, and direct report navigation.
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

      {/* Control Bar: Project, Search, Filter & Sort */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          {/* Project Selector */}
          <div>
            <label className="block text-xs font-medium text-slate-400 uppercase tracking-wider mb-1">
              Project
            </label>
            <select
              value={selectedProjectId}
              onChange={(e) => setSelectedProjectId(e.target.value)}
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-sky-500"
            >
              <option value="all">All Projects ({projects.length})</option>
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </div>

          {/* Status Filter */}
          <div>
            <label className="block text-xs font-medium text-slate-400 uppercase tracking-wider mb-1">
              Status
            </label>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-sky-500"
            >
              <option value="all">All Statuses</option>
              <option value="COMPLETED">Completed</option>
              <option value="RUNNING">Running</option>
              <option value="FAILED">Failed</option>
              <option value="CANCELLED">Cancelled</option>
              <option value="TIMED_OUT">Timed Out</option>
            </select>
          </div>

          {/* Run Type Filter */}
          <div>
            <label className="block text-xs font-medium text-slate-400 uppercase tracking-wider mb-1">
              Run Type
            </label>
            <select
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-sky-500"
            >
              <option value="all">All Run Types</option>
              <option value="STANDARD">Standard Analysis</option>
              <option value="VERIFICATION">Fix Verification</option>
            </select>
          </div>

          {/* Sort By */}
          <div>
            <label className="block text-xs font-medium text-slate-400 uppercase tracking-wider mb-1">
              Sort By
            </label>
            <div className="flex space-x-2">
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-sky-500"
              >
                <option value="started_at">Execution Time</option>
                <option value="flaky_count">Flaky Tests Count</option>
                <option value="total_tests">Total Tests</option>
                <option value="duration">Run Duration</option>
              </select>
              <button
                onClick={() => setSortOrder(sortOrder === 'desc' ? 'asc' : 'desc')}
                title={`Sort ${sortOrder === 'desc' ? 'Ascending' : 'Descending'}`}
                className="px-2.5 py-2 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-lg text-slate-300 text-xs flex items-center justify-center shrink-0"
              >
                <ArrowUpDown className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>

        {/* Search Bar */}
        <form onSubmit={handleSearchSubmit} className="flex gap-2">
          <div className="relative flex-1">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Search by project name or run ID..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-slate-800/80 border border-slate-700 rounded-lg pl-9 pr-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-sky-500"
            />
          </div>
          <button
            type="submit"
            className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 rounded-lg text-sm font-medium transition-colors"
          >
            Search
          </button>
          {(searchQuery || selectedProjectId !== 'all' || statusFilter !== 'all' || typeFilter !== 'all') && (
            <button
              type="button"
              onClick={() => {
                setSearchQuery('');
                setSelectedProjectId('all');
                setStatusFilter('all');
                setTypeFilter('all');
              }}
              className="px-3 py-2 text-slate-400 hover:text-slate-200 text-sm flex items-center space-x-1"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span>Reset</span>
            </button>
          )}
        </form>
      </div>

      {/* Main Runs Table / List */}
      {loading ? (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-12 text-center text-slate-400 text-sm">
          <Layers className="w-6 h-6 animate-spin mx-auto mb-2 text-sky-400" />
          Loading historical runs from database...
        </div>
      ) : error ? (
        <div className="p-4 bg-rose-950/30 border border-rose-800 rounded-xl text-rose-300 text-sm flex items-center justify-between">
          <span>{error}</span>
          <button
            onClick={fetchRuns}
            className="px-3 py-1 bg-rose-900/50 hover:bg-rose-900 text-rose-200 rounded text-xs font-medium"
          >
            Retry
          </button>
        </div>
      ) : runs.length === 0 ? (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
          <EmptyState
            icon={History}
            title="No Execution Runs Found"
            description={
              searchQuery || selectedProjectId !== 'all' || statusFilter !== 'all'
                ? 'No execution sessions matched your current filter or search criteria.'
                : 'No repeated test analysis runs have been initiated yet. Upload a project to begin.'
            }
            actionLabel="Start New Analysis"
            onAction={onNavigateToNew}
          />
        </div>
      ) : (
        <div className="space-y-3">
          <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider px-1">
            Displaying {runs.length} Execution Session(s)
          </div>

          {runs.map((run) => {
            const isVerification = run.run_type === 'VERIFICATION';
            return (
              <div
                key={run.id}
                className="bg-slate-900 border border-slate-800 hover:border-slate-700/80 transition-all rounded-xl p-4 sm:p-5 space-y-3"
              >
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                  <div className="space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-semibold text-white text-base">
                        {run.project_name || 'Project'}
                      </span>
                      {getStatusBadge(run.status)}
                      {isVerification ? (
                        <span className="inline-flex items-center space-x-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-purple-500/10 text-purple-400 border border-purple-500/30">
                          <ShieldCheck className="w-3 h-3" />
                          <span>Fix Verification</span>
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 rounded text-[11px] font-medium bg-slate-800 text-slate-300 border border-slate-700/60">
                          Standard Analysis
                        </span>
                      )}
                    </div>
                    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-400 font-mono">
                      <span>ID: {run.id.slice(0, 8)}...{run.id.slice(-4)}</span>
                      {run.started_at && (
                        <span>Started: {new Date(run.started_at).toLocaleString()}</span>
                      )}
                      {run.duration_seconds !== null && run.duration_seconds !== undefined && (
                        <span className="text-slate-300 flex items-center space-x-1">
                          <Clock className="w-3.5 h-3.5 text-sky-400" />
                          <span>{run.duration_seconds}s</span>
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Action Buttons */}
                  <div className="flex items-center space-x-2 self-start sm:self-auto">
                    <button
                      onClick={() => onNavigateToReport(run.id)}
                      className="inline-flex items-center space-x-1.5 px-3 py-1.5 bg-sky-600/20 hover:bg-sky-600/30 text-sky-300 border border-sky-500/30 rounded-lg text-xs font-medium transition-colors"
                    >
                      <FileBarChart2 className="w-3.5 h-3.5" />
                      <span>View Report</span>
                    </button>
                    <button
                      onClick={() => onNavigateToCompare(run.id)}
                      className="inline-flex items-center space-x-1.5 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 rounded-lg text-xs font-medium transition-colors"
                    >
                      <GitCompare className="w-3.5 h-3.5" />
                      <span>Compare</span>
                    </button>
                  </div>
                </div>

                {/* Summary Metrics Chips */}
                <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 pt-2 border-t border-slate-800/60">
                  <div className="p-2 rounded bg-slate-800/40 border border-slate-800/80">
                    <div className="text-[10px] text-slate-400 uppercase font-medium">Iterations</div>
                    <div className="text-sm font-bold text-white mt-0.5">
                      {run.completed_iterations ?? 0} / {run.iteration_count}
                    </div>
                  </div>

                  <div className="p-2 rounded bg-slate-800/40 border border-slate-800/80">
                    <div className="text-[10px] text-slate-400 uppercase font-medium">Total Tests</div>
                    <div className="text-sm font-bold text-white mt-0.5">{run.total_tests}</div>
                  </div>

                  <div className="p-2 rounded bg-slate-800/40 border border-slate-800/80">
                    <div className="text-[10px] text-emerald-400 uppercase font-medium">Passing</div>
                    <div className="text-sm font-bold text-emerald-400 mt-0.5">
                      {run.consistently_passing_count}
                    </div>
                  </div>

                  <div className="p-2 rounded bg-slate-800/40 border border-slate-800/80">
                    <div className="text-[10px] text-rose-400 uppercase font-medium">Failing</div>
                    <div className="text-sm font-bold text-rose-400 mt-0.5">
                      {run.consistently_failing_count}
                    </div>
                  </div>

                  <div className="p-2 rounded bg-slate-800/40 border border-slate-800/80 col-span-2 sm:col-span-1">
                    <div className="text-[10px] text-amber-400 uppercase font-medium">Flaky Tests</div>
                    <div className="text-sm font-bold text-amber-400 mt-0.5">
                      {run.flaky_tests_count}
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
