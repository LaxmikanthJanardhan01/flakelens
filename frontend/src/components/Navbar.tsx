import React, { useEffect, useState } from 'react';
import { Activity, ShieldCheck, AlertCircle, RefreshCw } from 'lucide-react';
import { healthApi } from '../services/api';
import { SystemHealth } from '../types';

export const Navbar: React.FC = () => {
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchHealth = async () => {
    setLoading(true);
    try {
      const data = await healthApi.getHealth();
      setHealth(data);
      setError(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Backend unreachable');
      setHealth(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchHealth();
    const interval = setInterval(fetchHealth, 30000); // Poll every 30s
    return () => clearInterval(interval);
  }, []);

  return (
    <header className="h-16 border-b border-slate-800 bg-slate-900/90 backdrop-blur sticky top-0 z-40 px-6 flex items-center justify-between">
      <div className="flex items-center space-x-3">
        <div className="p-2 bg-sky-600/20 border border-sky-500/30 rounded-lg text-sky-400">
          <Activity className="w-5 h-5" />
        </div>
        <div>
          <div className="flex items-center space-x-2">
            <span className="font-bold text-lg tracking-tight text-white">FLAKELENS</span>
            <span className="text-[10px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700">
              v0.1.0-alpha
            </span>
          </div>
          <p className="text-xs text-slate-400 hidden sm:block">
            Flaky Test Detection & Root Cause Analysis
          </p>
        </div>
      </div>

      <div className="flex items-center space-x-4">
        {/* Live Backend Health Pill */}
        <div className="flex items-center space-x-2 bg-slate-800/80 border border-slate-700/80 px-3 py-1.5 rounded-full text-xs">
          {loading ? (
            <>
              <RefreshCw className="w-3.5 h-3.5 animate-spin text-slate-400" />
              <span className="text-slate-400">Checking health...</span>
            </>
          ) : health && health.status === 'healthy' ? (
            <>
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
              </span>
              <span className="text-emerald-400 font-medium">Backend Healthy</span>
              <span className="text-slate-500 text-[10px]">({health.database})</span>
            </>
          ) : (
            <>
              <AlertCircle className="w-3.5 h-3.5 text-rose-400" />
              <span className="text-rose-400 font-medium">Disconnected</span>
              {error && <span className="text-slate-500 text-[10px] hidden md:inline">({error})</span>}
            </>
          )}
          <button
            onClick={fetchHealth}
            title="Refresh Health"
            className="text-slate-400 hover:text-slate-200 transition-colors ml-1"
          >
            <RefreshCw className="w-3 h-3" />
          </button>
        </div>

        <div className="hidden lg:flex items-center space-x-1 text-xs text-slate-400 bg-slate-800/50 px-2.5 py-1.5 rounded border border-slate-800">
          <ShieldCheck className="w-3.5 h-3.5 text-sky-400" />
          <span>Air-Gapped Sandbox: Phase 2 Ready</span>
        </div>
      </div>
    </header>
  );
};

