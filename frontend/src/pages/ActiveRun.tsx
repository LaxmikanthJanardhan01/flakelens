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

  const fetchRuns = useCallback(async () => {
    try {
      const res = await fetch('/api/runs');
      if (res.ok) {
        const data: TestRun[] = await res.json();
        setRunsList(data);
        if (!selectedRunId && data.length > 0) {
          const active = data.find((r) => r.status === 'RUNNING' || r.status === 'PENDING');
          setSelectedRunId(active ? active.id : data[0].id);
        }
      }
    } catch (err) {
      console.error('Failed to fetch runs:', err);
    }
  }, [selectedRunId]);

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
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium bg-[#EBF8F2] text-[#159B67] border border-[#A7E7CB]">
            <CheckCircle2 className="w-3 h-3 mr-1" /> PASSED
          </span>
        );
      case 'FAILED':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium bg-[#FDF2F2] text-[#DC4B4B] border border-[#F7BEBE]">
            <XCircle className="w-3 h-3 mr-1" /> FAILED
          </span>
        );
      case 'TIMED_OUT':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium bg-[#FEF8EC] text-[#D99A22] border border-[#FADDA8]">
            <Clock className="w-3 h-3 mr-1" /> TIMED OUT
          </span>
        );
      case 'NOT_EXECUTED':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium bg-[#F1F3F7] text-[#647084] border border-[#E5E9E8]">
            NOT EXECUTED
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium bg-[#F0FDFA] text-[#0F766E] border border-[#CCFBF1]">
            {status}
          </span>
        );
    }
  };

  // If no runs exist at all
  if (!isLoading && runsList.length === 0) {
    return (
      <div className="space-y-5">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-4 border-b border-[#E5E9E8]">
          <div>
            <h1 className="text-xl font-bold text-[#202A32] tracking-tight">Active Run Monitor</h1>
            <p className="text-xs text-[#647084] mt-0.5">
              Real-time iteration progress, streaming execution logs, and live telemetry.
            </p>
          </div>
        </div>
        <div className="bg-[#FFFFFF] border border-[#E5E9E8] rounded-lg p-6">
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
    <div className="space-y-5">
      {/* Header and Run Selector */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-4 border-b border-[#E5E9E8]">
        <div>
          <h1 className="text-xl font-bold text-[#202A32] tracking-tight">Active Run Monitor</h1>
          <p className="text-xs text-[#647084] mt-0.5">
            Real-time iteration progress, streaming execution logs, and live container telemetry.
          </p>
        </div>

        {runsList.length > 1 && (
          <div className="flex items-center space-x-2">
            <span className="text-xs text-[#647084] font-medium">Session:</span>
            <select
              value={selectedRunId || ''}
              onChange={(e) => setSelectedRunId(e.target.value)}
              className="bg-[#FFFFFF] border border-[#E5E9E8] text-xs text-[#202A32] rounded-md px-2.5 py-1.5 focus:outline-none focus:ring-1 focus:ring-[#0F766E] focus:border-[#0F766E]"
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
        <div className="p-3 bg-[#FDF2F2] border border-[#F7BEBE] rounded-md text-xs text-[#DC4B4B] flex items-center space-x-2">
          <AlertTriangle className="w-4 h-4 text-[#DC4B4B] shrink-0" />
          <span>{errorMsg}</span>
        </div>
      )}

      {/* Progress Card */}
      {runData && (
        <div className="p-5 bg-[#FFFFFF] border border-[#E5E9E8] rounded-lg shadow-card space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="space-y-1">
              <div className="flex items-center space-x-3">
                <span className="text-xs font-mono text-[#647084]">Run ID: {runData.id}</span>
                {getStatusBadge(runData.status)}
              </div>
              <div className="text-sm font-semibold text-[#202A32]">
                Progress: {runData.completed_iterations} of {runData.iteration_count} iterations completed ({progressPercent}%)
              </div>
            </div>

            <div className="flex items-center space-x-3">
              {(runData.status === 'RUNNING' || runData.status === 'PENDING') && (
                <button
                  onClick={handleCancelRun}
                  disabled={isCancelling}
                  className="inline-flex items-center px-3 py-1.5 rounded-md text-xs font-semibold bg-[#FDF2F2] hover:bg-[#F7BEBE] text-[#DC4B4B] border border-[#F7BEBE] transition-colors cursor-pointer"
                >
                  <StopCircle className="w-3.5 h-3.5 mr-1.5" />
                  {isCancelling ? 'Cancelling...' : 'Cancel Run'}
                </button>
              )}
              <button
                onClick={() => selectedRunId && fetchRunDetails(selectedRunId)}
                className="p-1.5 text-[#647084] hover:text-[#202A32] bg-[#FFFFFF] hover:bg-[#F7F8FA] rounded-md border border-[#E5E9E8] cursor-pointer"
                title="Refresh Telemetry"
              >
                <RefreshCw className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Progress Bar */}
          <div className="w-full bg-[#E5E9E8] rounded-full h-2.5 overflow-hidden">
            <div
              className={`h-2.5 rounded-full transition-all duration-500 ${
                runData.status === 'FAILED' || runData.status === 'TIMED_OUT'
                  ? 'bg-[#D99A22]'
                  : runData.status === 'COMPLETED'
                  ? 'bg-[#159B67]'
                  : 'bg-[#0F766E] animate-pulse'
              }`}
              style={{ width: `${progressPercent}%` }}
            />
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2 text-xs">
            <div className="p-2.5 bg-[#F7F8FA] rounded-md border border-[#E5E9E8]">
              <span className="text-[#647084]">Total Tests:</span>
              <div className="text-sm font-semibold text-[#202A32] mt-0.5">{runData.total_tests}</div>
            </div>
            <div className="p-2.5 bg-[#F7F8FA] rounded-md border border-[#E5E9E8]">
              <span className="text-[#647084]">Order Shuffling:</span>
              <div className="text-sm font-semibold text-[#202A32] mt-0.5">{runData.shuffle_order ? 'Enabled' : 'Disabled'}</div>
            </div>
            <div className="p-2.5 bg-[#F7F8FA] rounded-md border border-[#E5E9E8]">
              <span className="text-[#647084]">Completed Iterations:</span>
              <div className="text-sm font-semibold text-[#202A32] mt-0.5">{runData.completed_iterations} / {runData.iteration_count}</div>
            </div>
            <div className="p-2.5 bg-[#F7F8FA] rounded-md border border-[#E5E9E8]">
              <span className="text-[#647084]">Sandbox Isolation:</span>
              <div className="text-sm font-semibold text-[#159B67] mt-0.5">Air-Gapped (--network none)</div>
            </div>
          </div>
        </div>
      )}

      {/* Test Execution Stream */}
      <div className="bg-[#FFFFFF] border border-[#E5E9E8] rounded-lg overflow-hidden shadow-card">
        <div className="px-5 py-3.5 border-b border-[#E5E9E8] flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <Terminal className="w-4 h-4 text-[#0F766E]" />
            <h2 className="text-sm font-semibold text-[#202A32]">Live Execution Telemetry</h2>
          </div>
          <span className="text-xs text-[#647084]">
            {iterationsData.length} recorded test iteration outcomes
          </span>
        </div>

        {iterationsData.length === 0 ? (
          <div className="p-8 text-center text-xs text-[#647084]">
            {runData?.status === 'PENDING'
              ? 'Starting Docker container and preparing runner environment...'
              : 'No test outcomes recorded yet for this session.'}
          </div>
        ) : (
          <div className="divide-y divide-[#E5E9E8] max-h-[550px] overflow-y-auto">
            {iterationsData.map((item) => {
              const isExpanded = expandedRow === item.id;
              return (
                <div key={item.id} className="hover:bg-[#F7F8FA] transition-colors">
                  <div
                    onClick={() => setExpandedRow(isExpanded ? null : item.id)}
                    className="px-5 py-3 flex items-center justify-between cursor-pointer text-xs"
                  >
                    <div className="flex items-center space-x-3 truncate pr-4">
                      <button className="text-[#647084] hover:text-[#202A32]">
                        {isExpanded ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
                      </button>
                      <span className="font-mono text-[#647084] w-14 shrink-0">
                        Iter #{item.iteration_number}
                      </span>
                      <span className="font-medium text-[#202A32] truncate font-mono">
                        {item.node_id}
                      </span>
                    </div>

                    <div className="flex items-center space-x-3 shrink-0">
                      <span className="font-mono text-[#647084]">{item.duration_ms}ms</span>
                      {getStatusBadge(item.status)}
                    </div>
                  </div>

                  {/* Expandable Traceback and Logs */}
                  {isExpanded && (
                    <div className="px-5 pb-4 pt-1 bg-[#F1F3F7] border-t border-[#E5E9E8] space-y-2 text-xs">
                      {item.random_order_seed && (
                        <div className="text-[11px] text-[#647084] font-mono">
                          Random-order seed: <span className="text-[#0F766E]">{item.random_order_seed}</span> (Execution order: #{item.execution_order})
                        </div>
                      )}

                      {item.error_message && (
                        <pre className="p-3 rounded-md bg-[#FDF2F2] border border-[#F7BEBE] text-[#DC4B4B] font-mono text-[11px] overflow-x-auto whitespace-pre">
                          {item.error_message}
                        </pre>
                      )}

                      {item.traceback && (
                        <pre className="p-3 rounded-md bg-[#F1F3F7] border border-[#E5E9E8] text-[#202A32] font-mono text-[11px] overflow-x-auto whitespace-pre">
                          {item.traceback}
                        </pre>
                      )}

                      {item.stdout && (
                        <div>
                          <div className="text-[11px] text-[#647084] mb-1 font-semibold">Standard Output (stdout):</div>
                          <pre className="p-3 rounded-md bg-[#F1F3F7] border border-[#E5E9E8] text-[#202A32] font-mono text-[11px] overflow-x-auto whitespace-pre">
                            {item.stdout}
                          </pre>
                        </div>
                      )}

                      {item.stderr && (
                        <div>
                          <div className="text-[11px] text-[#647084] mb-1 font-semibold">Standard Error (stderr):</div>
                          <pre className="p-3 rounded-md bg-[#FDF2F2] border border-[#F7BEBE] text-[#DC4B4B] font-mono text-[11px] overflow-x-auto whitespace-pre">
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
