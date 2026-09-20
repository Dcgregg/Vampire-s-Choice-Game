import React, { useEffect } from 'react';
import { useGameState } from '../../state/useGameState';
import confetti from 'canvas-confetti';
import { Trophy, X, Sparkles } from 'lucide-react';
import { useTrustedProgression } from '../../progression/useTrustedProgression';

export const AchievementBanner: React.FC = () => {
  const { newlyUnlockedAchievement, dismissAchievementBanner, setScreen } = useGameState();
  const trusted = useTrustedProgression();
  const trustedAccount = trusted.enabled && trusted.accountActive;

  useEffect(() => {
    if (newlyUnlockedAchievement && !trustedAccount) {
      try {
        // Subtle burst of crimson & gold sparks
        confetti({
          particleCount: 35,
          spread: 55,
          origin: { y: 0.25 },
          colors: ['#be123c', '#c5a059', '#e5c158', '#4c0519', '#ffffff'],
          disableForReducedMotion: true,
        });
      } catch {
        // Canvas confetti fallback
      }
    }
  }, [newlyUnlockedAchievement, trustedAccount]);

  if (!newlyUnlockedAchievement || trustedAccount) return null;

  return (
    <div className="fixed top-16 left-1/2 z-50 w-[92%] max-w-md -translate-x-1/2 transform transition-all duration-500 animate-in fade-in slide-in-from-top-4">
      <div className="relative overflow-hidden rounded-xl border border-[#c5a059]/60 bg-[#140e1c] p-4 shadow-[0_10px_30px_rgba(0,0,0,0.8),0_0_20px_rgba(190,18,60,0.3)]">
        {/* Ornate corner accents */}
        <div className="absolute top-0 left-0 h-4 w-4 border-t-2 border-l-2 border-[#c5a059]" />
        <div className="absolute top-0 right-0 h-4 w-4 border-t-2 border-r-2 border-[#c5a059]" />
        <div className="absolute bottom-0 left-0 h-4 w-4 border-b-2 border-l-2 border-[#c5a059]" />
        <div className="absolute bottom-0 right-0 h-4 w-4 border-b-2 border-r-2 border-[#c5a059]" />

        <div className="flex items-start gap-3">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-[#c5a059]/40 bg-gradient-to-br from-rose-950 via-[#1c1226] to-black text-[#e5c158] shadow-inner">
            <Trophy className="h-5 w-5 animate-pulse" />
          </div>

          <div className="flex-1 pr-6">
            <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-[#e5c158]">
              <Sparkles className="h-3 w-3" />
              <span>Achievement Unlocked</span>
            </div>
            <h4 className="font-display text-sm font-bold text-[#f5f0e6]">
              {newlyUnlockedAchievement.title}
            </h4>
            <p className="mt-0.5 text-xs text-[#d6cbbe] leading-relaxed">
              {newlyUnlockedAchievement.description}
            </p>

            <div className="mt-2.5 flex items-center gap-3">
              <button
                onClick={() => {
                  dismissAchievementBanner();
                  setScreen('achievements');
                }}
                className="text-[11px] font-semibold text-[#fae092] hover:underline"
              >
                View in Trophies →
              </button>
            </div>
          </div>

          <button
            onClick={dismissAchievementBanner}
            className="absolute top-3 right-3 rounded-md p-1 text-stone-400 hover:text-stone-100 hover:bg-white/10"
            title="Dismiss"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );
};
