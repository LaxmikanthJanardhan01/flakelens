import React from 'react';
import {
  LayoutDashboard,
  UploadCloud,
  PlayCircle,
  FileBarChart2,
  GitCompare,
} from 'lucide-react';

export type NavigationTab =
  | 'dashboard'
  | 'new-analysis'
  | 'active-run'
  | 'reports'
  | 'diff-inspector';

interface SidebarProps {
  activeTab: NavigationTab;
  onSelectTab: (tab: NavigationTab) => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ activeTab, onSelectTab }) => {
  const navItems = [
    {
      id: 'dashboard' as NavigationTab,
      label: 'Overview',
      icon: LayoutDashboard,
      description: 'System health & recent runs',
    },
    {
      id: 'new-analysis' as NavigationTab,
      label: 'New Analysis',
      icon: UploadCloud,
      description: 'Upload project & configure',
    },
    {
      id: 'active-run' as NavigationTab,
      label: 'Active Run',
      icon: PlayCircle,
      description: 'Live execution monitor',
    },
    {
      id: 'reports' as NavigationTab,
      label: 'Flakiness Reports',
      icon: FileBarChart2,
      description: 'Tri-bucket analysis & scores',
    },
    {
      id: 'diff-inspector' as NavigationTab,
      label: 'Diff Inspector',
      icon: GitCompare,
      description: 'Pass vs fail execution diffs',
    },
  ];

  return (
    <aside className="w-64 border-r border-slate-800 bg-slate-900/60 p-4 flex flex-col justify-between shrink-0">
      <div className="space-y-1">
        <div className="px-3 py-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
          Navigation
        </div>
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onSelectTab(item.id)}
              className={`w-full flex items-center space-x-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all ${
                isActive
                  ? 'bg-sky-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
              }`}
            >
              <Icon className={`w-4 h-4 ${isActive ? 'text-white' : 'text-slate-400'}`} />
              <div className="text-left">
                <div>{item.label}</div>
              </div>
            </button>
          );
        })}
      </div>

      <div className="p-3 bg-slate-800/40 rounded-lg border border-slate-800 text-xs text-slate-400">
        <div className="font-semibold text-slate-300 mb-1">Phase 1: Architecture</div>
        <p className="text-[11px] text-slate-400">
          Models, API contracts, and UI shell initialized. Docker execution scheduled for Phase 2.
        </p>
      </div>
    </aside>
  );
};

