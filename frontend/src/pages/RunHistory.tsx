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
          <span className="inline-flex items-center space-x-1 px-2.5 py-0.5 rounded text-[11px] font-medium bg-[#EBF8F2] text-[#159B67] border border-[#A7E7CB]">
            <CheckCircle2 className="w-3 h-3" />
            <span>Completed</span>
          </span>
        );
      case 'RUNNING':
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-0.5 rounded text-[11px] font-medium bg-[#F0FDFA] text-[#0F766E] border border-[#CCFBF1]">
            <Layers className="w-3 h-3 animate-spin" />
            <span>Running</span>
          </span>
        );
      case 'FAILED':
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-0.5 rounded text-[11px] font-medium bg-[#FDF2F2] text-[#DC4B4B] border border-[#F7BEBE]">
            <XCircle className="w-3 h-3" />
            <span>Failed</span>
          </span>
        );
      case 'CANCELLED':
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-0.5 rounded text-[11px] font-medium bg-[#FEF8EC] text-[#D99A22] border border-[#FADDA8]">
            <AlertTriangle className="w-3 h-3" />
            <span>Cancelled</span>
          </span>
        );
      case 'TIMED_OUT':
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-0.5 rounded text-[11px] font-medium bg-[#FDF2F2] text-[#DC4B4B] border border-[#F7BEBE]">
            <Clock className="w-3 h-3" />
            <span>Timed Out</span>
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-0.5 rounded text-[11px] font-medium bg-[#F1F3F7] text-[#647084] border border-[#E5E9E8]">
            <span>{status}</span>
          </span>
        );
    }
  };

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-4 border-b border-[#E5E9E8]">
        <div>
          <h1 className="text-xl font-bold text-[#202A32] tracking-tight">Project Run History</h1>
          <p className="text-xs text-[#647084] mt-0.5">
            Historical execution sessions across projects with search, multi-factor filtering, and direct report navigation.
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

      {/* Control Bar */}
      <div className="bg-[#FFFFFF] border border-[#E5E9E8] rounded-lg p-4 space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          {/* Project Selector */}
          <div>
            <label className="block text-xs font-medium text-[#647084] uppercase tracking-wider mb-1">
              Project
            </label>
            <select
              value={selectedProjectId}
              onChange={(e) => setSelectedProjectId(e.target.value)}
              className="w-full bg-[#FFFFFF] border border-[#E5E9E8] rounded-md px-3 py-2 text-sm text-[#202A32] focus:outline-none focus:ring-1 focus:ring-[#0F766E] focus:border-[#0F766E]"
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
            <label className="block text-xs font-medium text-[#647084] uppercase tracking-wider mb-1">
              Status
            </label>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="w-full bg-[#FFFFFF] border border-[#E5E9E8] rounded-md px-3 py-2 text-sm text-[#202A32] focus:outline-none focus:ring-1 focus:ring-[#0F766E] focus:border-[#0F766E]"
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
            <label className="block text-xs font-medium text-[#647084] uppercase tracking-wider mb-1">
              Run Type
            </label>
            <select
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
              className="w-full bg-[#FFFFFF] border border-[#E5E9E8] rounded-md px-3 py-2 text-sm text-[#202A32] focus:outline-none focus:ring-1 focus:ring-[#0F766E] focus:border-[#0F766E]"
            >
              <option value="all">All Run Types</option>
              <option value="STANDARD">Standard Analysis</option>
              <option value="VERIFICATION">Fix Verification</option>
            </select>
          </div>

          {/* Sort By */}
          <div>
            <label className="block text-xs font-medium text-[#647084] uppercase tracking-wider mb-1">
              Sort By
            </label>
            <div className="flex space-x-2">
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value)}
                className="w-full bg-[#FFFFFF] border border-[#E5E9E8] rounded-md px-3 py-2 text-sm text-[#202A32] focus:outline-none focus:ring-1 focus:ring-[#0F766E] focus:border-[#0F766E]"
              >
                <option value="started_at">Execution Time</option>
                <option value="flaky_count">Flaky Tests Count</option>
                <option value="total_tests">Total Tests</option>
                <option value="duration">Run Duration</option>
              </select>
              <button
                onClick={() => setSortOrder(sortOrder === 'desc' ? 'asc' : 'desc')}
                title={`Sort ${sortOrder === 'desc' ? 'Ascending' : 'Descending'}`}
                className="px-2.5 py-2 bg-[#FFFFFF] hover:bg-[#F7F8FA] border border-[#E5E9E8] rounded-md text-[#647084] text-xs flex items-center justify-center shrink-0 cursor-pointer"
              >
                <ArrowUpDown className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>

        {/* Search Bar */}
        <form onSubmit={handleSearchSubmit} className="flex gap-2">
          <div className="relative flex-1">
            <Search className="w-4 h-4 text-[#8993A2] absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Search by project name or run ID..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full px-3 py-2 pl-9 bg-[#FFFFFF] border border-[#E5E9E8] rounded-md text-sm text-[#202A32] placeholder-[#8993A2] focus:outline-none focus:ring-1 focus:ring-[#0F766E] focus:border-[#0F766E] transition-colors"
            />
          </div>
          <button
            type="submit"
            className="inline-flex items-center space-x-1.5 px-3 py-1.5 bg-[#FFFFFF] hover:bg-[#F7F8FA] text-[#202A32] border border-[#E5E9E8] rounded-md text-xs transition-colors cursor-pointer"
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
              className="px-3 py-1.5 text-[#647084] hover:text-[#202A32] text-xs flex items-center space-x-1 cursor-pointer"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span>Reset</span>
            </button>
          )}
        </form>
      </div>

      {/* Main Runs List */}
      {loading ? (
        <div className="bg-[#FFFFFF] border border-[#E5E9E8] rounded-lg p-12 text-center text-[#647084] text-sm">
          <Layers className="w-6 h-6 animate-spin mx-auto mb-2 text-[#0F766E]" />
          Loading historical runs from database...
        </div>
      ) : error ? (
        <div className="p-4 bg-[#FDF2F2] border border-[#F7BEBE] rounded-lg text-[#DC4B4B] text-sm flex items-center justify-between">
          <span>{error}</span>
          <button
            onClick={fetchRuns}
            className="px-3 py-1 bg-[#FDF2F2] hover:bg-[#F7BEBE] text-[#DC4B4B] border border-[#F7BEBE] rounded text-xs font-medium cursor-pointer"
          >
            Retry
          </button>
        </div>
      ) : runs.length === 0 ? (
        <div className="bg-[#FFFFFF] border border-[#E5E9E8] rounded-lg p-6">
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
          <div className="text-xs font-semibold text-[#647084] uppercase tracking-wider px-1">
            Displaying {runs.length} Execution Session(s)
          </div>

          {runs.map((run) => {
            const isVerification = run.run_type === 'VERIFICATION';
            return (
              <div
                key={run.id}
                className="bg-[#FFFFFF] border border-[#E5E9E8] hover:border-[#CBD5E1] transition-all rounded-lg p-4 sm:p-5 space-y-3"
              >
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                  <div className="space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-semibold text-[#202A32] text-sm">
                        {run.project_name || 'Project'}
                      </span>
                      {getStatusBadge(run.status)}
                      {isVerification ? (
                        <span className="inline-flex items-center space-x-1 px-2.5 py-0.5 rounded text-[11px] font-medium bg-[#F0FDFA] text-[#0F766E] border border-[#CCFBF1]">
                          <ShieldCheck className="w-3 h-3" />
                          <span>Fix Verification</span>
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 rounded text-[11px] font-medium bg-[#F7F8FA] border border-[#E5E9E8] text-[#647084]">
                          Standard Analysis
                        </span>
                      )}
                    </div>
                    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-[#647084] font-mono">
                      <span>ID: {run.id.slice(0, 8)}...{run.id.slice(-4)}</span>
                      {run.started_at && (
                        <span>Started: {new Date(run.started_at).toLocaleString()}</span>
                      )}
                      {run.duration_seconds !== null && run.duration_seconds !== undefined && (
                        <span className="text-[#202A32] flex items-center space-x-1">
                          <Clock className="w-3.5 h-3.5 text-[#0F766E]" />
                          <span>{run.duration_seconds}s</span>
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Action Buttons */}
                  <div className="flex items-center space-x-2 self-start sm:self-auto">
                    <button
                      onClick={() => onNavigateToReport(run.id)}
                      className="inline-flex items-center space-x-1.5 px-3 py-1.5 bg-[#F0FDFA] hover:bg-[#CCFBF1] text-[#0F766E] border border-[#CCFBF1] rounded-md text-xs font-medium transition-colors cursor-pointer"
                    >
                      <FileBarChart2 className="w-3.5 h-3.5" />
                      <span>View Report</span>
                    </button>
                    <button
                      onClick={() => onNavigateToCompare(run.id)}
                      className="inline-flex items-center space-x-1.5 px-3 py-1.5 bg-[#FFFFFF] hover:bg-[#F7F8FA] text-[#202A32] border border-[#E5E9E8] rounded-md text-xs font-medium transition-colors cursor-pointer"
                    >
                      <GitCompare className="w-3.5 h-3.5" />
                      <span>Compare</span>
                    </button>
                  </div>
                </div>

                {/* Summary Metrics Chips */}
                <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 pt-2 border-t border-[#E5E9E8]">
                  <div className="p-2 rounded bg-[#F7F8FA] border border-[#E5E9E8]">
                    <div className="text-[10px] text-[#647084] uppercase font-medium">Iterations</div>
                    <div className="text-sm font-bold text-[#202A32] mt-0.5">
                      {run.completed_iterations ?? 0} / {run.iteration_count}
                    </div>
                  </div>

                  <div className="p-2 rounded bg-[#F7F8FA] border border-[#E5E9E8]">
                    <div className="text-[10px] text-[#647084] uppercase font-medium">Total Tests</div>
                    <div className="text-sm font-bold text-[#202A32] mt-0.5">{run.total_tests}</div>
                  </div>

                  <div className="p-2 rounded bg-[#EBF8F2] border border-[#A7E7CB]">
                    <div className="text-[10px] text-[#159B67] uppercase font-medium">Passing</div>
                    <div className="text-sm font-bold text-[#159B67] mt-0.5">
                      {run.consistently_passing_count}
                    </div>
                  </div>

                  <div className="p-2 rounded bg-[#FDF2F2] border border-[#F7BEBE]">
                    <div className="text-[10px] text-[#DC4B4B] uppercase font-medium">Failing</div>
                    <div className="text-sm font-bold text-[#DC4B4B] mt-0.5">
                      {run.consistently_failing_count}
                    </div>
                  </div>

                  <div className="p-2 rounded bg-[#FEF8EC] border border-[#FADDA8] col-span-2 sm:col-span-1">
                    <div className="text-[10px] text-[#D99A22] uppercase font-medium">Flaky Tests</div>
                    <div className="text-sm font-bold text-[#D99A22] mt-0.5">
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
