import React, { useState, useEffect, useCallback } from 'react';
import {
  PlayCircle,
  CheckCircle2,
  XCircle,
  Clock,
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  RefreshCw,
  StopCircle,
  Terminal,
} from 'lucide-react';
import { EmptyState } from '../components/EmptyState';

interface ActiveRunProps {
  onNavigateToNew: () => void;
  runId?: string;
}

interface TestRun {
  id: string;
  project_id: string;
  iteration_count: number;
  completed_iterations: number;
  shuffle_order: boolean;
  status: string;
  total_tests: number;
  started_at: string | null;
  completed_at: string | null;
}

interface TestIterationDetail {
  id: string;
  test_run_id: string;
  test_case_id: string;
  node_id: string;
  test_name: string;
  file_path: string;
  iteration_number: number;
  status: string;
  duration_ms: number;
  execution_order: number;
  random_order_seed: number | null;
  stdout: string | null;
  stderr: string | null;
  error_message: string | null;
  traceback: string | null;
}

export const ActiveRun: React.FC<ActiveRunProps> = ({ onNavigateToNew, runId }) => {
  const [selectedRunId, setSelectedRunId] = useState<string | null>(runId || null);
  const [runsList, setRunsList] = useState<TestRun[]>([]);
  const [runData, setRunData] = useState<TestRun | null>(null);
  const [iterationsData, setIterationsData] = useState<TestIterationDetail[]>([]);
  const [expandedRow, setExpandedRow] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isCancelling, setIsCancelling] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Fetch list of recent runs if no specific runId provided
  const fetchRuns = useCallback(async () => {
    try {
      const res = await fetch('/api/runs');
      if (res.ok) {
        const data: TestRun[] = await res.json();
        setRunsList(data);
        if (!selectedRunId && data.length > 0) {
          // Default to latest active or latest completed run
          const active = data.find((r) => r.status === 'RUNNING' || r.status === 'PENDING');
          setSelectedRunId(active ? active.id : data[0].id);
        }
      }
    } catch (err) {
      console.error('Failed to fetch runs:', err);
    }
  }, [selectedRunId]);

  // Fetch details for the selected run
  const fetchRunDetails = useCallback(async (id: string) => {
    try {
      const [runRes, iterRes] = await Promise.all([
        fetch(`/api/runs/${id}`),
        fetch(`/api/runs/${id}/iterations`),
      ]);

      if (runRes.ok) {
        const rData: TestRun = await runRes.json();
        setRunData(rData);
      }
      if (iterRes.ok) {
        const iData: TestIterationDetail[] = await iterRes.json();
        setIterationsData(iData);
      }
      setErrorMsg(null);
    } catch (err) {
      console.error('Failed to fetch run telemetry:', err);
      setErrorMsg('Failed to connect to backend telemetry service.');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchRuns();
  }, [fetchRuns]);

  useEffect(() => {
    if (!selectedRunId) return;

    fetchRunDetails(selectedRunId);

    // Poll every 1.5s if run is active
    const interval = setInterval(() => {
      if (runData?.status === 'RUNNING' || runData?.status === 'PENDING') {
        fetchRunDetails(selectedRunId);
      }
    }, 1500);

    return () => clearInterval(interval);
  }, [selectedRunId, runData?.status, fetchRunDetails]);

  const handleCancelRun = async () => {
    if (!selectedRunId) return;
    setIsCancelling(true);
    try {
      const res = await fetch(`/api/runs/${selectedRunId}/cancel`, { method: 'POST' });
      if (res.ok) {
        const updated = await res.json();
        setRunData(updated);
      }
    } catch (err) {
      console.error('Failed to cancel run:', err);
    } finally {
      setIsCancelling(false);
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'PASSED':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-emerald-950/80 text-emerald-400 border border-emerald-800/60">
            <CheckCircle2 className="w-3 h-3 mr-1" /> PASSED
          </span>
        );
      case 'FAILED':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-rose-950/80 text-rose-400 border border-rose-800/60">
            <XCircle className="w-3 h-3 mr-1" /> FAILED
          </span>
        );
      case 'TIMED_OUT':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-amber-950/80 text-amber-400 border border-amber-800/60">
            <Clock className="w-3 h-3 mr-1" /> TIMED OUT
          </span>
        );
      case 'NOT_EXECUTED':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-slate-800 text-slate-400 border border-slate-700">
            NOT EXECUTED
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-sky-950/80 text-sky-400 border border-sky-800/60">
            {status}
          </span>
        );
    }
  };

  // If no runs exist at all
  if (!isLoading && runsList.length === 0) {
    return (
      <div className="space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-4 border-b border-slate-800">
          <div>
            <h1 className="text-2xl font-bold text-white tracking-tight">Active Run Monitor</h1>
            <p className="text-sm text-slate-400 mt-1">
              Real-time iteration progress, streaming execution logs, and live telemetry.
            </p>
          </div>
        </div>
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
          <EmptyState
            icon={PlayCircle}
            title="No Active Test Run"
            description="There are currently no test execution sessions recorded. Upload a project archive to start repeated test execution."
            actionLabel="Launch New Analysis"
            onAction={onNavigateToNew}
          />
        </div>
      </div>
    );
  }

  const progressPercent = runData
    ? Math.min(100, Math.round((runData.completed_iterations / runData.iteration_count) * 100))
    : 0;

  return (
    <div className="space-y-6">
      {/* Header and Run Selector */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-4 border-b border-slate-800">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Active Run Monitor</h1>
          <p className="text-sm text-slate-400 mt-1">
            Real-time iteration progress, streaming execution logs, and live container telemetry.
          </p>
        </div>

        {runsList.length > 1 && (
          <div className="flex items-center space-x-2">
            <span className="text-xs text-slate-400 font-medium">Session:</span>
            <select
              value={selectedRunId || ''}
              onChange={(e) => setSelectedRunId(e.target.value)}
              className="bg-slate-800 border border-slate-700 text-xs text-white rounded-lg px-2.5 py-1.5 focus:outline-none focus:border-sky-500"
            >
              {runsList.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.id.slice(0, 8)} ({r.status}) - {r.completed_iterations}/{r.iteration_count}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      {errorMsg && (
        <div className="p-3 bg-rose-950/60 border border-rose-800 rounded-lg text-xs text-rose-300 flex items-center space-x-2">
          <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
          <span>{errorMsg}</span>
        </div>
      )}

      {/* Progress Card */}
      {runData && (
        <div className="p-6 bg-slate-900 border border-slate-800 rounded-xl space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="space-y-1">
              <div className="flex items-center space-x-3">
                <span className="text-xs font-mono text-slate-400">Run ID: {runData.id}</span>
                {getStatusBadge(runData.status)}
              </div>
              <div className="text-sm font-semibold text-white">
                Progress: {runData.completed_iterations} of {runData.iteration_count} iterations completed ({progressPercent}%)
              </div>
            </div>

            <div className="flex items-center space-x-3">
              {(runData.status === 'RUNNING' || runData.status === 'PENDING') && (
                <button
                  onClick={handleCancelRun}
                  disabled={isCancelling}
                  className="inline-flex items-center px-3 py-1.5 rounded-lg text-xs font-semibold bg-rose-950/80 hover:bg-rose-900 text-rose-300 border border-rose-800 transition-colors"
                >
                  <StopCircle className="w-3.5 h-3.5 mr-1.5" />
                  {isCancelling ? 'Cancelling...' : 'Cancel Run'}
                </button>
              )}
              <button
                onClick={() => selectedRunId && fetchRunDetails(selectedRunId)}
                className="p-1.5 text-slate-400 hover:text-white bg-slate-800 hover:bg-slate-700 rounded-lg border border-slate-700"
                title="Refresh Telemetry"
              >
                <RefreshCw className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Progress Bar */}
          <div className="w-full bg-slate-800 rounded-full h-2.5 overflow-hidden">
            <div
              className={`h-2.5 rounded-full transition-all duration-500 ${
                runData.status === 'FAILED' || runData.status === 'TIMED_OUT'
                  ? 'bg-amber-500'
                  : runData.status === 'COMPLETED'
                  ? 'bg-emerald-500'
                  : 'bg-sky-500 animate-pulse'
              }`}
              style={{ width: `${progressPercent}%` }}
            />
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2 text-xs">
            <div className="p-2.5 bg-slate-800/40 rounded-lg border border-slate-800">
              <span className="text-slate-400">Total Tests:</span>
              <div className="text-sm font-semibold text-white mt-0.5">{runData.total_tests}</div>
            </div>
            <div className="p-2.5 bg-slate-800/40 rounded-lg border border-slate-800">
              <span className="text-slate-400">Order Shuffling:</span>
              <div className="text-sm font-semibold text-white mt-0.5">{runData.shuffle_order ? 'Enabled' : 'Disabled'}</div>
            </div>
            <div className="p-2.5 bg-slate-800/40 rounded-lg border border-slate-800">
              <span className="text-slate-400">Completed Iterations:</span>
              <div className="text-sm font-semibold text-white mt-0.5">{runData.completed_iterations} / {runData.iteration_count}</div>
            </div>
            <div className="p-2.5 bg-slate-800/40 rounded-lg border border-slate-800">
              <span className="text-slate-400">Sandbox Isolation:</span>
              <div className="text-sm font-semibold text-emerald-400 mt-0.5">Air-Gapped (--network none)</div>
            </div>
          </div>
        </div>
      )}

      {/* Test Execution Stream */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <Terminal className="w-4 h-4 text-sky-400" />
            <h2 className="text-base font-semibold text-white">Live Execution Telemetry</h2>
          </div>
          <span className="text-xs text-slate-400">
            {iterationsData.length} recorded test iteration outcomes
          </span>
        </div>

        {iterationsData.length === 0 ? (
          <div className="p-8 text-center text-xs text-slate-400">
            {runData?.status === 'PENDING'
              ? 'Starting Docker container and preparing runner environment...'
              : 'No test outcomes recorded yet for this session.'}
          </div>
        ) : (
          <div className="divide-y divide-slate-800/60 max-h-[550px] overflow-y-auto">
            {iterationsData.map((item) => {
              const isExpanded = expandedRow === item.id;
              return (
                <div key={item.id} className="hover:bg-slate-800/20 transition-colors">
                  <div
                    onClick={() => setExpandedRow(isExpanded ? null : item.id)}
                    className="px-6 py-3 flex items-center justify-between cursor-pointer text-xs"
                  >
                    <div className="flex items-center space-x-3 truncate pr-4">
                      <button className="text-slate-500 hover:text-white">
                        {isExpanded ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
                      </button>
                      <span className="font-mono text-slate-400 w-14 shrink-0">
                        Iter #{item.iteration_number}
                      </span>
                      <span className="font-medium text-slate-200 truncate font-mono">
                        {item.node_id}
                      </span>
                    </div>

                    <div className="flex items-center space-x-3 shrink-0">
                      <span className="font-mono text-slate-400">{item.duration_ms}ms</span>
                      {getStatusBadge(item.status)}
                    </div>
                  </div>

                  {/* Expandable Traceback and Logs */}
                  {isExpanded && (
                    <div className="px-6 pb-4 pt-1 bg-slate-950/60 border-t border-slate-800/40 space-y-2 text-xs">
                      {item.random_order_seed && (
                        <div className="text-[11px] text-slate-400 font-mono">
                          Random-order seed: <span className="text-sky-300">{item.random_order_seed}</span> (Execution order: #{item.execution_order})
                        </div>
                      )}

                      {item.error_message && (
                        <div className="p-2.5 rounded bg-rose-950/30 border border-rose-900/40 text-rose-300 font-mono text-[11px] whitespace-pre-wrap">
                          {item.error_message}
                        </div>
                      )}

                      {item.traceback && (
                        <div className="p-2.5 rounded bg-slate-900 border border-slate-800 text-slate-300 font-mono text-[11px] overflow-x-auto whitespace-pre">
                          {item.traceback}
                        </div>
                      )}

                      {item.stdout && (
                        <div>
                          <div className="text-[11px] text-slate-400 mb-1 font-semibold">Standard Output (stdout):</div>
                          <pre className="p-2 rounded bg-slate-900 border border-slate-800 text-slate-300 font-mono text-[11px] overflow-x-auto whitespace-pre">
                            {item.stdout}
                          </pre>
                        </div>
                      )}

                      {item.stderr && (
                        <div>
                          <div className="text-[11px] text-slate-400 mb-1 font-semibold">Standard Error (stderr):</div>
                          <pre className="p-2 rounded bg-slate-900 border border-slate-800 text-rose-300 font-mono text-[11px] overflow-x-auto whitespace-pre">
                            {item.stderr}
                          </pre>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
