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
    <div className="space-y-6 max-w-4xl mx-auto">
      <div>
        <h1 className="text-2xl font-bold text-white tracking-tight">Configure New Analysis</h1>
        <p className="text-sm text-slate-400 mt-1">
          Upload a Python project archive and configure repetitive execution parameters to uncover non-deterministic tests.
        </p>
      </div>

      {errorMessage && (
        <div className="p-3 bg-rose-950/60 border border-rose-800 rounded-lg text-xs text-rose-300 flex items-center space-x-2">
          <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
          <span>{errorMessage}</span>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Left Column: Form Settings */}
        <div className="md:col-span-2 space-y-6">
          {/* File Upload Box */}
          <div className="p-6 bg-slate-900 border border-slate-800 rounded-xl space-y-4">
            <h2 className="text-base font-semibold text-white flex items-center space-x-2">
              <FileArchive className="w-4 h-4 text-sky-400" />
              <span>Project Source Ingestion</span>
            </h2>

            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1">
                Project Name
              </label>
              <input
                type="text"
                placeholder="e.g. backend-api-suite"
                value={projectName}
                onChange={(e) => setProjectName(e.target.value)}
                className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-white placeholder-slate-500 focus:outline-none focus:border-sky-500"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1">
                Upload Project Archive (.zip)
              </label>
              <div className="border-2 border-dashed border-slate-700 hover:border-sky-500 rounded-xl p-6 text-center transition-colors cursor-pointer bg-slate-800/30">
                <input
                  type="file"
                  accept=".zip"
                  onChange={handleFileChange}
                  className="hidden"
                  id="project-file-input"
                />
                <label htmlFor="project-file-input" className="cursor-pointer">
                  <UploadCloud className="w-10 h-10 text-slate-400 mx-auto mb-2" />
                  <div className="text-sm font-medium text-slate-200">
                    {archiveFile ? archiveFile.name : 'Click to select project archive (.zip)'}
                  </div>
                  <p className="text-xs text-slate-500 mt-1">
                    Pytest project repository with tests/ or test_*.py
                  </p>
                </label>
              </div>
            </div>

            {archiveFile && !projectId && (
              <button
                onClick={handleUploadAndDiscover}
                disabled={isUploading}
                className="w-full py-2.5 px-4 bg-sky-600 hover:bg-sky-500 disabled:bg-slate-800 text-white font-medium text-xs rounded-lg transition-colors flex items-center justify-center space-x-2"
              >
                <Search className="w-4 h-4" />
                <span>{isUploading ? 'Extracting & Discovering in Docker...' : 'Upload & Discover Tests'}</span>
              </button>
            )}

            {projectId && (
              <div className="p-3 bg-emerald-950/40 border border-emerald-800/60 rounded-lg flex items-center justify-between text-xs text-emerald-300">
                <div className="flex items-center space-x-2">
                  <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                  <span>Ingested successfully! Discovered {discoveredCount} test cases.</span>
                </div>
              </div>
            )}
          </div>

          {/* Execution Parameters */}
          <div className="p-6 bg-slate-900 border border-slate-800 rounded-xl space-y-4">
            <h2 className="text-base font-semibold text-white flex items-center space-x-2">
              <Sliders className="w-4 h-4 text-sky-400" />
              <span>Repetition Parameters</span>
            </h2>

            <div>
              <div className="flex justify-between items-center text-xs font-medium text-slate-300 mb-1">
                <span>Repetition Count (N):</span>
                <span className="font-mono text-sky-400 font-bold">{iterations} iterations</span>
              </div>
              <input
                type="range"
                min="3"
                max="20"
                value={iterations}
                onChange={(e) => setIterations(Number(e.target.value))}
                className="w-full accent-sky-500 h-2 bg-slate-700 rounded-lg cursor-pointer"
              />
              <div className="flex justify-between text-[10px] text-slate-500 mt-1">
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
                  className="mt-1 rounded bg-slate-800 border-slate-700 text-sky-600 focus:ring-0"
                />
                <div>
                  <div className="text-sm font-medium text-slate-200">
                    Randomize Test Execution Order
                  </div>
                  <div className="text-xs text-slate-400">
                    Enables deterministic random ordering via <code className="text-sky-300 font-mono">pytest-random-order</code> to uncover hidden state pollution.
                  </div>
                </div>
              </label>
            </div>

            {projectId && (
              <div className="pt-4 border-t border-slate-800">
                <button
                  onClick={handleStartRun}
                  disabled={isStarting || discoveredCount === 0}
                  className="w-full py-3 px-4 bg-emerald-600 hover:bg-emerald-500 disabled:bg-slate-800 text-white font-bold text-sm rounded-lg transition-colors flex items-center justify-center space-x-2 shadow-lg shadow-emerald-950/40"
                >
                  <Play className="w-4 h-4" />
                  <span>{isStarting ? 'Initiating Isolated Execution...' : `Launch Analysis Run (${iterations} Iterations)`}</span>
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Right Column: Discovery Preview */}
        <div className="space-y-6">
          <div className="p-6 bg-slate-900 border border-slate-800 rounded-xl">
            <h2 className="text-base font-semibold text-white flex items-center space-x-2 mb-2">
              <Search className="w-4 h-4 text-sky-400" />
              <span>Test Discovery Preview</span>
            </h2>
            <p className="text-xs text-slate-400 mb-4">
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
                  <div key={t.id} className="p-2.5 rounded-lg bg-slate-800/40 border border-slate-800 text-xs">
                    <div className="font-medium text-slate-200 truncate">{t.test_name}</div>
                    <div className="text-[11px] font-mono text-slate-400 truncate">{t.file_path}</div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="p-4 rounded-xl bg-slate-800/30 border border-slate-800 space-y-2 text-xs text-slate-400">
            <div className="flex items-center space-x-1.5 font-semibold text-slate-300">
              <Shield className="w-3.5 h-3.5 text-sky-400" />
              <span>Docker Sandbox Enforced</span>
            </div>
            <p className="text-[11px] leading-relaxed">
              Execution runs strictly inside isolated Docker containers with non-root UID 1000,
              <code className="text-sky-300 font-mono">--network none</code>, and read-only project mounts.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
