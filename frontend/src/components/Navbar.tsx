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
    <header className="h-14 border-b border-[#E5E9E8] bg-[#FFFFFF] sticky top-0 z-40 px-6 flex items-center justify-between shadow-[0_1px_2px_rgba(0,0,0,0.03)]">
      <div className="flex items-center space-x-3">
        <div className="w-8 h-8 rounded-md bg-[#F0FDFA] border border-[#CCFBF1] flex items-center justify-center text-[#0F766E]">
          <Activity className="w-4 h-4" />
        </div>
        <div>
          <div className="flex items-center space-x-2">
            <span className="font-semibold text-base tracking-tight text-[#202A32]">FLAKELENS</span>
            <span className="text-[10px] font-medium tracking-wide px-1.5 py-0.5 rounded bg-[#F1F3F7] text-[#647084] border border-[#E5E9E8]">
              v0.3.0
            </span>
          </div>
          <p className="text-[11px] text-[#647084] hidden sm:block leading-tight">
            Flaky Test Detection &amp; Root Cause Analysis
          </p>
        </div>
      </div>

      <div className="flex items-center space-x-3">
        {/* Live Backend Health Pill */}
        <div className="flex items-center space-x-2 bg-[#FFFFFF] border border-[#E5E9E8] px-2.5 py-1 rounded-full text-xs shadow-sm">
          {loading ? (
            <>
              <RefreshCw className="w-3.5 h-3.5 animate-spin text-[#647084]" />
              <span className="text-[#647084] text-[11px]">Checking health...</span>
            </>
          ) : health && health.status === 'healthy' ? (
            <>
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#159B67] opacity-60"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-[#159B67]"></span>
              </span>
              <span className="text-[#159B67] font-medium text-[11px]">Backend Healthy</span>
              <span className="text-[#647084] text-[10px] tabular-nums">({health.database})</span>
            </>
          ) : (
            <>
              <AlertCircle className="w-3.5 h-3.5 text-[#DC4B4B]" />
              <span className="text-[#DC4B4B] font-medium text-[11px]">Disconnected</span>
              {error && <span className="text-[#647084] text-[10px] hidden md:inline">({error})</span>}
            </>
          )}
          <button
            onClick={fetchHealth}
            title="Refresh Health"
            className="text-[#647084] hover:text-[#202A32] transition-colors ml-0.5 p-0.5 cursor-pointer"
          >
            <RefreshCw className="w-3 h-3" />
          </button>
        </div>

        {/* Sandbox indicator with bright teal accent */}
        <div className="hidden lg:flex items-center space-x-1.5 text-xs text-[#647084] bg-[#F7F8FA] px-2.5 py-1 rounded-md border border-[#E5E9E8]">
          <ShieldCheck className="w-3.5 h-3.5 text-[#14B8A6]" />
          <span className="text-[11px] font-medium">Air-Gapped Sandbox: Active</span>
        </div>
      </div>
    </header>
  );
};
