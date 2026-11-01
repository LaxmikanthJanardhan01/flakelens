import React, { useState } from 'react';
import { UploadCloud, Sliders, Shield, FileArchive, Search } from 'lucide-react';
import { EmptyState } from '../components/EmptyState';

export const NewAnalysis: React.FC = () => {
  const [projectName, setProjectName] = useState<string>('');
  const [iterations, setIterations] = useState<number>(10);
  const [shuffleOrder, setShuffleOrder] = useState<boolean>(true);
  const [archiveFile, setArchiveFile] = useState<File | null>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      setArchiveFile(file);
      if (!projectName) {
        setProjectName(file.name.replace(/\.[^/.]+$/, ''));
      }
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
                  accept=".zip,.tar.gz"
                  onChange={handleFileChange}
                  className="hidden"
                  id="project-file-input"
                />
                <label htmlFor="project-file-input" className="cursor-pointer">
                  <UploadCloud className="w-10 h-10 text-slate-400 mx-auto mb-2" />
                  <div className="text-sm font-medium text-slate-200">
                    {archiveFile ? archiveFile.name : 'Click to select project archive'}
                  </div>
                  <p className="text-xs text-slate-500 mt-1">
                    Python pytest project with requirements.txt or pyproject.toml
                  </p>
                </label>
              </div>
            </div>
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
                    Enables the <code className="text-sky-300 font-mono">pytest-random-order</code> plugin to expose hidden state pollution and test dependencies.
                  </div>
                </div>
              </label>
            </div>
          </div>
        </div>

        {/* Right Column: Discovery Preview (Empty State) */}
        <div className="space-y-6">
          <div className="p-6 bg-slate-900 border border-slate-800 rounded-xl">
            <h2 className="text-base font-semibold text-white flex items-center space-x-2 mb-2">
              <Search className="w-4 h-4 text-sky-400" />
              <span>Test Discovery Preview</span>
            </h2>
            <p className="text-xs text-slate-400 mb-4">
              Discovered pytest functions will appear here after project collection.
            </p>

            <EmptyState
              icon={Search}
              title="No Tests Discovered Yet"
              description="Upload an archive to trigger pytest --collect-only indexing."
            />
          </div>

          <div className="p-4 rounded-xl bg-slate-800/30 border border-slate-800 space-y-2 text-xs text-slate-400">
            <div className="flex items-center space-x-1.5 font-semibold text-slate-300">
              <Shield className="w-3.5 h-3.5 text-sky-400" />
              <span>Phase 1 Scaffolding Notice</span>
            </div>
            <p className="text-[11px] leading-relaxed">
              Execution triggers will connect to the two-stage Docker runner in Phase 2.
              No arbitrary code runs on the host system.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
