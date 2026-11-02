import React from 'react';
import {
  LayoutDashboard,
  UploadCloud,
  PlayCircle,
  FileBarChart2,
  GitCompare,
  History,
} from 'lucide-react';

export type NavigationTab =
  | 'dashboard'
  | 'new-analysis'
  | 'active-run'
  | 'reports'
  | 'diff-inspector'
  | 'history';

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
    },
    {
      id: 'history' as NavigationTab,
      label: 'Run History',
      icon: History,
    },
    {
      id: 'new-analysis' as NavigationTab,
      label: 'New Analysis',
      icon: UploadCloud,
    },
    {
      id: 'active-run' as NavigationTab,
      label: 'Active Run',
      icon: PlayCircle,
    },
    {
      id: 'reports' as NavigationTab,
      label: 'Detailed Reports',
      icon: FileBarChart2,
    },
    {
      id: 'diff-inspector' as NavigationTab,
      label: 'Comparisons & Diffs',
      icon: GitCompare,
    },
  ];

  return (
    <aside className="w-56 border-r border-[#E5E9E8] bg-[#FFFFFF] p-3 flex flex-col justify-between shrink-0 shadow-[1px_0_2px_rgba(0,0,0,0.01)]">
      <div className="space-y-1">
        <div className="px-2.5 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-[#647084]">
          Workspace
        </div>
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onSelectTab(item.id)}
              className={`w-full flex items-center space-x-2.5 px-2.5 py-2 rounded-md text-xs font-medium transition-all cursor-pointer ${
                isActive
                  ? 'bg-[#F0FDFA] text-[#0F766E] border border-[#CCFBF1] font-semibold shadow-xs'
                  : 'text-[#647084] hover:text-[#202A32] hover:bg-[#F7F8FA] border border-transparent'
              }`}
            >
              <Icon className={`w-4 h-4 ${isActive ? 'text-[#0F766E]' : 'text-[#647084]'}`} />
              <span className="truncate">{item.label}</span>
            </button>
          );
        })}
      </div>

      <div className="p-3 bg-[#F7F8FA] rounded-md border border-[#E5E9E8] text-xs">
        <div className="font-semibold text-[#202A32] text-[11px] mb-0.5">Phase 3: Analysis Engine</div>
        <p className="text-[11px] text-[#647084] leading-relaxed">
          Automated flakiness scoring, root cause analysis, run diffing, and fix verification.
        </p>
      </div>
    </aside>
  );
};
