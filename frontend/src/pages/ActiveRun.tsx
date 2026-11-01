import React from 'react';
import { PlayCircle, ShieldCheck, Terminal } from 'lucide-react';
import { EmptyState } from '../components/EmptyState';

interface ActiveRunProps {
  onNavigateToNew: () => void;
}

export const ActiveRun: React.FC<ActiveRunProps> = ({ onNavigateToNew }) => {
  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-4 border-b border-slate-800">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Active Run Monitor</h1>
          <p className="text-sm text-slate-400 mt-1">
            Real-time iteration progress, streaming execution logs, and early flip detection.
          </p>
        </div>
      </div>

      {/* Main Empty State */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
        <EmptyState
          icon={PlayCircle}
          title="No Active Test Run"
          description="There is currently no test execution session in progress. Once initiated in Phase 2, this screen will stream real-time iteration results, live container stdout/stderr logs, and notify you as soon as an intermittent failure is detected."
          actionLabel="Launch New Analysis"
          onAction={onNavigateToNew}
        />
      </div>

      {/* Two-Stage Sandbox Architecture Overview */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="p-4 bg-slate-800/30 border border-slate-800 rounded-xl space-y-2">
          <div className="flex items-center space-x-2 text-sm font-semibold text-slate-200">
            <Terminal className="w-4 h-4 text-sky-400" />
            <span>Planned Live Log Streaming (Phase 2)</span>
          </div>
          <p className="text-xs text-slate-400 leading-relaxed">
            FastAPI will stream Server-Sent Events (SSE) directly from the running container, capturing console outputs and pytest outcomes on every single iteration.
          </p>
        </div>

        <div className="p-4 bg-slate-800/30 border border-slate-800 rounded-xl space-y-2">
          <div className="flex items-center space-x-2 text-sm font-semibold text-slate-200">
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
            <span>Air-Gapped Container Isolation (Phase 2)</span>
          </div>
          <p className="text-xs text-slate-400 leading-relaxed">
            During execution, the runner container enforces <code className="text-sky-300 font-mono">--network none</code> to eliminate network jitter and ensure untrusted test code cannot contact external networks.
          </p>
        </div>
      </div>
    </div>
  );
};
