import React, { useState } from 'react';
import { UploadCloud, Sliders, Shield, FileArchive, Search, CheckCircle2, Play, AlertCircle } from 'lucide-react';
import { EmptyState } from '../components/EmptyState';

interface NewAnalysisProps {
  onRunStarted?: (runId: string) => void;
}

interface DiscoveredTestCase {
  id: string;
  file_path: string;
  test_name: string;
  node_id: string;
}

export const NewAnalysis: React.FC<NewAnalysisProps> = ({ onRunStarted }) => {
  const [projectName, setProjectName] = useState<string>('');
  const [iterations, setIterations] = useState<number>(5);
  const [shuffleOrder, setShuffleOrder] = useState<boolean>(true);
  const [archiveFile, setArchiveFile] = useState<File | null>(null);

  const [isUploading, setIsUploading] = useState<boolean>(false);
  const [isStarting, setIsStarting] = useState<boolean>(false);
  const [projectId, setProjectId] = useState<string | null>(null);
  const [discoveredCount, setDiscoveredCount] = useState<number>(0);
  const [testsList, setTestsList] = useState<DiscoveredTestCase[]>([]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      setArchiveFile(file);
      if (!projectName) {
        setProjectName(file.name.replace(/\.[^/.]+$/, ''));
      }
      setProjectId(null);
      setTestsList([]);
      setErrorMessage(null);
    }
  };

  const handleUploadAndDiscover = async () => {
    if (!archiveFile) return;
    setIsUploading(true);
    setErrorMessage(null);

    const formData = new FormData();
    formData.append('file', archiveFile);
    if (projectName.trim()) {
      formData.append('name', projectName.trim());
    }

    try {
      const res = await fetch('/api/projects/upload', {
        method: 'POST',
        body: formData,
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Upload failed with HTTP ${res.status}`);
      }

      const projData = await res.json();
      setProjectId(projData.id);
      setDiscoveredCount(projData.test_cases_count || 0);

      // Fetch discovered test items
      const testsRes = await fetch(`/api/projects/${projData.id}/tests`);
      if (testsRes.ok) {
        const testsData = await testsRes.json();
        setTestsList(testsData);
      }
    } catch (err: any) {
      console.error('Project ingestion error:', err);
      setErrorMessage(err.message || 'Failed to ingest project archive.');
    } finally {
      setIsUploading(false);
    }
  };

  const handleStartRun = async () => {
    if (!projectId) return;
    setIsStarting(true);
    setErrorMessage(null);

    try {
      const res = await fetch('/api/runs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_id: projectId,
          iteration_count: iterations,
          shuffle_order: shuffleOrder,
        }),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Failed to start run (HTTP ${res.status})`);
      }

      const runData = await res.json();
      if (onRunStarted) {
        onRunStarted(runData.id);
      }
    } catch (err: any) {
      console.error('Start run error:', err);
      setErrorMessage(err.message || 'Failed to start execution run.');
    } finally {
      setIsStarting(false);
    }
  };

  return (
    <div className="space-y-5 max-w-4xl mx-auto">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-4 border-b border-[#E5E9E8]">
        <div>
          <h1 className="text-xl font-bold text-[#202A32] tracking-tight">Configure New Analysis</h1>
          <p className="text-xs text-[#647084] mt-0.5">
            Upload a Python project archive and configure repetitive execution parameters to uncover non-deterministic tests.
          </p>
        </div>
      </div>

      {errorMessage && (
        <div className="p-3 bg-[#FDF2F2] border border-[#F7BEBE] rounded-md text-xs text-[#DC4B4B] flex items-center space-x-2">
          <AlertCircle className="w-4 h-4 text-[#DC4B4B] shrink-0" />
          <span>{errorMessage}</span>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Left Column: Form Settings */}
        <div className="md:col-span-2 space-y-5">
          {/* File Upload Box */}
          <div className="p-5 bg-[#FFFFFF] border border-[#E5E9E8] rounded-lg shadow-card space-y-4">
            <h2 className="text-sm font-semibold text-[#202A32] flex items-center space-x-2">
              <FileArchive className="w-4 h-4 text-[#0F766E]" />
              <span>Project Source Ingestion</span>
            </h2>

            <div>
              <label className="block text-xs font-medium text-[#647084] mb-1">
                Project Name
              </label>
              <input
                type="text"
                placeholder="e.g. backend-api-suite"
                value={projectName}
                onChange={(e) => setProjectName(e.target.value)}
                className="w-full px-3 py-2 bg-[#FFFFFF] border border-[#E5E9E8] rounded-md text-sm text-[#202A32] placeholder-[#8993A2] focus:outline-none focus:ring-1 focus:ring-[#0F766E] focus:border-[#0F766E] transition-colors"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-[#647084] mb-1">
                Upload Project Archive (.zip)
              </label>
              <div className="border-2 border-dashed border-[#E5E9E8] hover:border-[#0F766E] rounded-lg p-6 text-center transition-colors cursor-pointer bg-[#F7F8FA]">
                <input
                  type="file"
                  accept=".zip"
                  onChange={handleFileChange}
                  className="hidden"
                  id="project-file-input"
                />
                <label htmlFor="project-file-input" className="cursor-pointer">
                  <UploadCloud className="w-10 h-10 text-[#8993A2] mx-auto mb-2" />
                  <div className="text-sm font-medium text-[#202A32]">
                    {archiveFile ? archiveFile.name : 'Click to select project archive (.zip)'}
                  </div>
                  <p className="text-xs text-[#647084] mt-1">
                    Pytest project repository with tests/ or test_*.py
                  </p>
                </label>
              </div>
            </div>

            {archiveFile && !projectId && (
              <button
                onClick={handleUploadAndDiscover}
                disabled={isUploading}
                className="w-full py-2.5 px-4 bg-[#0F766E] hover:bg-[#0D6860] disabled:bg-[#F1F5F5] disabled:text-[#8993A2] text-white font-medium text-xs rounded-md transition-colors flex items-center justify-center space-x-2 cursor-pointer"
              >
                <Search className="w-4 h-4" />
                <span>{isUploading ? 'Extracting & Discovering in Docker...' : 'Upload & Discover Tests'}</span>
              </button>
            )}

            {projectId && (
              <div className="p-3 bg-[#EBF8F2] border border-[#A7E7CB] rounded-md flex items-center justify-between text-xs text-[#159B67]">
                <div className="flex items-center space-x-2">
                  <CheckCircle2 className="w-4 h-4 text-[#159B67] shrink-0" />
                  <span>Ingested successfully! Discovered {discoveredCount} test cases.</span>
                </div>
              </div>
            )}
          </div>

          {/* Execution Parameters */}
          <div className="p-5 bg-[#FFFFFF] border border-[#E5E9E8] rounded-lg shadow-card space-y-4">
            <h2 className="text-sm font-semibold text-[#202A32] flex items-center space-x-2">
              <Sliders className="w-4 h-4 text-[#0F766E]" />
              <span>Repetition Parameters</span>
            </h2>

            <div>
              <div className="flex justify-between items-center text-xs font-medium text-[#647084] mb-1">
                <span>Repetition Count (N):</span>
                <span className="font-mono text-[#0F766E] font-bold">{iterations} iterations</span>
              </div>
              <input
                type="range"
                min="3"
                max="20"
                value={iterations}
                onChange={(e) => setIterations(Number(e.target.value))}
                className="w-full accent-[#0F766E] h-2 bg-[#E5E9E8] rounded-lg cursor-pointer"
              />
              <div className="flex justify-between text-[10px] text-[#8993A2] mt-1">
                <span>3 (Fast triage)</span>
                <span>5 (Standard)</span>
                <span>10 (Recommended)</span>
                <span>20 (Deep audit)</span>
              </div>
            </div>

            <div className="pt-2">
              <label className="flex items-start space-x-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={shuffleOrder}
                  onChange={(e) => setShuffleOrder(e.target.checked)}
                  className="mt-1 rounded border-[#E5E9E8] text-[#0F766E] focus:ring-0"
                />
                <div>
                  <div className="text-sm font-medium text-[#202A32]">
                    Randomize Test Execution Order
                  </div>
                  <div className="text-xs text-[#647084]">
                    Enables deterministic random ordering via <code className="text-[#0F766E] font-mono">pytest-random-order</code> to uncover hidden state pollution.
                  </div>
                </div>
              </label>
            </div>

            {projectId && (
              <div className="pt-4 border-t border-[#E5E9E8]">
                <button
                  onClick={handleStartRun}
                  disabled={isStarting || discoveredCount === 0}
                  className="w-full py-3 px-4 bg-[#0F766E] hover:bg-[#0D6860] disabled:bg-[#F1F5F5] disabled:text-[#8993A2] text-white font-bold text-sm rounded-md transition-colors flex items-center justify-center space-x-2 shadow-sm cursor-pointer"
                >
                  <Play className="w-4 h-4" />
                  <span>{isStarting ? 'Initiating Isolated Execution...' : `Launch Analysis Run (${iterations} Iterations)`}</span>
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Right Column: Discovery Preview */}
        <div className="space-y-5">
          <div className="p-5 bg-[#FFFFFF] border border-[#E5E9E8] rounded-lg shadow-card">
            <h2 className="text-sm font-semibold text-[#202A32] flex items-center space-x-2 mb-2">
              <Search className="w-4 h-4 text-[#0F766E]" />
              <span>Test Discovery Preview</span>
            </h2>
            <p className="text-xs text-[#647084] mb-4">
              Discovered pytest functions running strictly inside Docker container.
            </p>

            {testsList.length === 0 ? (
              <EmptyState
                icon={Search}
                title="No Tests Discovered Yet"
                description="Upload an archive to trigger pytest --collect-only inside Docker."
              />
            ) : (
              <div className="space-y-2 max-h-[350px] overflow-y-auto">
                {testsList.map((t) => (
                  <div key={t.id} className="p-2.5 rounded-md bg-[#F7F8FA] border border-[#E5E9E8] text-xs">
                    <div className="font-medium text-[#202A32] truncate">{t.test_name}</div>
                    <div className="text-[11px] font-mono text-[#647084] truncate">{t.file_path}</div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="p-4 rounded-lg bg-[#F0FDFA] border border-[#CCFBF1] space-y-2 text-xs text-[#647084]">
            <div className="flex items-center space-x-1.5 font-semibold text-[#0F766E]">
              <Shield className="w-3.5 h-3.5 text-[#0F766E]" />
              <span>Docker Sandbox Enforced</span>
            </div>
            <p className="text-[11px] leading-relaxed">
              Execution runs strictly inside isolated Docker containers with non-root UID 1000,
              <code className="text-[#0F766E] font-mono"> --network none</code>, and read-only project mounts.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
