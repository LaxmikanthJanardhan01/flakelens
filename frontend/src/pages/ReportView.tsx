import React, { useState } from 'react';
import { FileBarChart2, Filter, AlertTriangle, XCircle, CheckCircle2 } from 'lucide-react';
import { EmptyState } from '../components/EmptyState';

interface ReportViewProps {
  onNavigateToNew: () => void;
}

export const ReportView: React.FC<ReportViewProps> = ({ onNavigateToNew }) => {
  const [filter, setFilter] = useState<'ALL' | 'FLAKY' | 'FAILING' | 'PASSING'>('ALL');

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-4 border-b border-slate-800">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Flakiness Analysis Reports</h1>
          <p className="text-sm text-slate-400 mt-1">
            Tri-part outcome classification, flakiness score rankings, and evidence-based root cause diagnoses.
          </p>
        </div>
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
          <span>All Outcomes</span>
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
          <span>Flaky (Intermittent)</span>
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
          <span>Consistently Failing (Deterministic Bugs)</span>
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
          <span>Consistently Passing (Stable)</span>
        </button>
      </div>

      {/* Main Empty State */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
        <EmptyState
          icon={FileBarChart2}
          title="No Flakiness Reports Available"
          description="Reports will be synthesized here in Phase 3 after tests are executed across multiple iterations. FLAKELENS will calculate the Flakiness Score S for intermittent tests and isolate deterministic bugs."
          actionLabel="Execute Test Suite"
          onAction={onNavigateToNew}
        />
      </div>

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
            Non-deterministic outcome. Scored by flakiness formula and analyzed for root cause.
          </p>
        </div>
      </div>
    </div>
  );
};

