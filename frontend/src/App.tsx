import React, { useState } from 'react';
import { Navbar } from './components/Navbar';
import { Sidebar, NavigationTab } from './components/Sidebar';
import { Dashboard } from './pages/Dashboard';
import { NewAnalysis } from './pages/NewAnalysis';
import { ActiveRun } from './pages/ActiveRun';
import { ReportView } from './pages/ReportView';
import { DiffInspector } from './pages/DiffInspector';

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<NavigationTab>('dashboard');
  const [activeRunId, setActiveRunId] = useState<string | null>(null);

  const handleRunStarted = (runId: string) => {
    setActiveRunId(runId);
    setActiveTab('active-run');
  };

  return (
    <div className="min-h-screen flex flex-col bg-slate-950 text-slate-100">
      <Navbar />

      <div className="flex-1 flex overflow-hidden">
        <Sidebar activeTab={activeTab} onSelectTab={setActiveTab} />

        <main className="flex-1 overflow-y-auto p-6 md:p-8 bg-slate-900/40">
          <div className="max-w-7xl mx-auto">
            {activeTab === 'dashboard' && (
              <Dashboard onNavigateToNew={() => setActiveTab('new-analysis')} />
            )}
            {activeTab === 'new-analysis' && (
              <NewAnalysis onRunStarted={handleRunStarted} />
            )}
            {activeTab === 'active-run' && (
              <ActiveRun
                runId={activeRunId || undefined}
                onNavigateToNew={() => setActiveTab('new-analysis')}
              />
            )}
            {activeTab === 'reports' && (
              <ReportView onNavigateToNew={() => setActiveTab('new-analysis')} />
            )}
            {activeTab === 'diff-inspector' && <DiffInspector />}
          </div>
        </main>
      </div>
    </div>
  );
};

export default App;
