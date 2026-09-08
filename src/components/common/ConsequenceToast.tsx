import React, { useEffect } from 'react';
import { useGameState } from '../../state/useGameState';
import { Sparkles, X } from 'lucide-react';

export const ConsequenceToast: React.FC = () => {
  const { latestConsequence, clearConsequenceToast } = useGameState();

  useEffect(() => {
    if (latestConsequence) {
      const timer = setTimeout(() => {
        clearConsequenceToast();
      }, 4200);
      return () => clearTimeout(timer);
    }
  }, [latestConsequence, clearConsequenceToast]);

  if (!latestConsequence) return null;

  return (
    <div className="pointer-events-none fixed bottom-20 left-1/2 z-50 w-[90%] max-w-sm -translate-x-1/2 transform transition-all duration-300 animate-in fade-in slide-in-from-bottom-3">
      <div className="pointer-events-auto flex items-center justify-between rounded-full border border-[#c5a059]/40 bg-[#140e1d]/95 px-4 py-2.5 shadow-[0_4px_20px_rgba(0,0,0,0.8),0_0_15px_rgba(190,18,60,0.25)] backdrop-blur-md">
        <div className="flex items-center gap-2.5 overflow-hidden">
          <Sparkles className="h-4 w-4 shrink-0 text-[#e5c158] animate-spin" />
          <span className="font-interface text-xs font-medium text-[#ede5d8] truncate">
            {latestConsequence.message}
          </span>
        </div>
        <button
          onClick={clearConsequenceToast}
          className="ml-2 shrink-0 rounded-full p-1 text-stone-400 hover:text-white"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
};
