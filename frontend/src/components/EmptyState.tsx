import React from 'react';
import { LucideIcon } from 'lucide-react';

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description: string;
  actionLabel?: string;
  onAction?: () => void;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  icon: Icon,
  title,
  description,
  actionLabel,
  onAction,
}) => {
  return (
    <div className="flex flex-col items-center justify-center p-10 text-center rounded-lg border border-dashed border-[#CBD5E1] bg-[#FFFFFF] my-6 shadow-xs">
      <div className="w-10 h-10 rounded-full bg-[#F1F5F9] border border-[#E5E9E8] mb-3 flex items-center justify-center text-[#647084]">
        <Icon className="w-5 h-5 text-[#647084]" />
      </div>
      <h3 className="text-sm font-semibold text-[#202A32] mb-1">{title}</h3>
      <p className="text-xs text-[#647084] max-w-md mb-4 leading-relaxed">{description}</p>
      {actionLabel && onAction && (
        <button
          onClick={onAction}
          className="px-3.5 py-1.5 text-xs font-medium text-white bg-[#0F766E] hover:bg-[#0D6860] rounded-md transition-colors shadow-sm cursor-pointer"
        >
          {actionLabel}
        </button>
      )}
    </div>
  );
};
