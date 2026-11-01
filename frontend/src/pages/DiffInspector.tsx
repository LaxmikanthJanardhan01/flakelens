import React from 'react';
import { GitCompare, Clock, Terminal, AlertOctagon } from 'lucide-react';
import { EmptyState } from '../components/EmptyState';

export const DiffInspector: React.FC = () => {
  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-4 border-b border-slate-800">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Run Comparison & Diff Inspector</h1>
          <p className="text-sm text-slate-400 mt-1">
            Side-by-side execution evidence comparing passing and failing iterations for intermittent tests.
          </p>
        </div>
      </div>

      {/* Main Empty State */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
        <EmptyState
          icon={GitCompare}
          title="No Test Selected for Inspection"
          description="In Phase 4, selecting a flaky test from the Flakiness Reports view will load a side-by-side comparison of its passing iteration vs. failing iteration, highlighting execution duration deltas, console outputs, and traceback signatures."
        />
      </div>

      {/* Telemetry Diff Capabilities Overview */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="p-4 bg-slate-800/30 border border-slate-800 rounded-xl space-y-2">
          <div className="flex items-center space-x-2 text-sm font-semibold text-slate-200">
            <Clock className="w-4 h-4 text-sky-400" />
            <span>Duration Variance Delta</span>
          </div>
          <p className="text-xs text-slate-400 leading-relaxed">
            Identifies execution time spikes and timeouts between green and red iterations to uncover timing and sleep race conditions.
          </p>
        </div>

        <div className="p-4 bg-slate-800/30 border border-slate-800 rounded-xl space-y-2">
          <div className="flex items-center space-x-2 text-sm font-semibold text-sky-400">
            <Terminal className="w-4 h-4 text-sky-400" />
            <span>Console Output Diff</span>
          </div>
          <p className="text-xs text-slate-400 leading-relaxed">
            Performs unified line diffs on stdout and stderr logs captured per iteration by the pytest JSON collector.
          </p>
        </div>

        <div className="p-4 bg-slate-800/30 border border-slate-800 rounded-xl space-y-2">
          <div className="flex items-center space-x-2 text-sm font-semibold text-amber-400">
            <AlertOctagon className="w-4 h-4 text-amber-400" />
            <span>Heuristic RCA Suggestions</span>
          </div>
          <p className="text-xs text-slate-400 leading-relaxed">
            Maps traceback exception types (<code className="text-amber-300 font-mono">EADDRINUSE</code>, <code className="text-amber-300 font-mono">TimeoutError</code>) to concrete, actionable fixture refactoring recommendations.
          </p>
        </div>
      </div>
    </div>
  );
};
