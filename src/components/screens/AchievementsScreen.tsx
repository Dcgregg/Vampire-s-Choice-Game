import React from 'react';
import { useGameState } from '../../state/useGameState';
import { Trophy, CheckCircle2, Lock, Sparkles, Award } from 'lucide-react';
import { useTrustedProgression } from '../../progression/useTrustedProgression';

export const AchievementsScreen: React.FC = () => {
  const { state } = useGameState();
  const trusted = useTrustedProgression();
  const achievements = Object.values(state.achievements);
  const authoritativeAchievements = trusted.enabled && trusted.accountActive
    ? trusted.confirmedAchievements
    : null;
  const unlockedCount = authoritativeAchievements
    ? Object.keys(authoritativeAchievements).length
    : achievements.filter((a) => a.unlockedAt).length;

  const getRarityBadge = (rarity: string) => {
    switch (rarity) {
      case 'Gothic Legend':
        return 'text-[#fae092] border-[#c5a059]/60 bg-[#2b1b36]';
      case 'Rare':
        return 'text-rose-300 border-rose-900/60 bg-rose-950/40';
      case 'Common':
      default:
        return 'text-stone-300 border-white/10 bg-black/40';
    }
  };

  return (
    <div className="mx-auto max-w-lg px-4 py-6 pb-24 space-y-5">
      {/* Header */}
      <div className="text-center">
        <span className="text-[10px] uppercase tracking-widest text-[#e5c158] font-semibold">
          Hall of Nocturne Deeds
        </span>
        <h2 className="font-display text-2xl font-bold text-[#f5f0e6] mt-1">
          Trophies & Milestones
        </h2>
        <p className="font-narrative italic text-xs text-[#d6cbbe] mt-1">
          {unlockedCount} of {achievements.length} achievements unlocked
        </p>

        {/* Global Progress */}
        <div className="mt-3 h-2 w-full max-w-xs mx-auto rounded-full bg-black/60 overflow-hidden border border-white/10">
          <div
            className="h-full bg-gradient-to-r from-rose-700 via-[#c5a059] to-rose-700 transition-all duration-500 rounded-full"
            style={{ width: `${(unlockedCount / achievements.length) * 100}%` }}
          />
        </div>
      </div>

      {/* Achievement Cards */}
      <div className="space-y-3">
        {achievements.map((ach) => {
          const authoritative = authoritativeAchievements?.[ach.id];
          const isUnlocked = authoritativeAchievements
            ? Boolean(authoritative)
            : Boolean(ach.unlockedAt);
          const unlockedAt = authoritative?.unlockedAt ?? ach.unlockedAt;
          const rarityBadge = getRarityBadge(ach.rarity);

          return (
            <div
              key={ach.id}
              className={`relative overflow-hidden rounded-xl border p-4 transition-all ${
                isUnlocked
                  ? 'border-[#c5a059]/50 bg-gradient-to-r from-[#1b1026] to-[#120a1b] shadow-md shadow-rose-950/20'
                  : 'border-white/5 bg-black/30 opacity-65'
              }`}
            >
              {isUnlocked && (
                <div className="absolute top-0 right-0 h-16 w-16 overflow-hidden pointer-events-none">
                  <div className="absolute transform rotate-45 bg-[#c5a059] text-black text-[9px] font-bold py-0.5 right-[-35px] top-[18px] w-[120px] text-center shadow">
                    UNLOCKED
                  </div>
                </div>
              )}

              <div className="flex items-start gap-3.5">
                {/* Icon */}
                <div
                  className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border text-lg shadow-inner ${
                    isUnlocked
                      ? 'border-[#c5a059] bg-[#221330] text-[#fae092]'
                      : 'border-white/10 bg-stone-900 text-stone-600'
                  }`}
                >
                  {isUnlocked ? <Trophy className="w-5 h-5 text-[#fae092]" /> : <Lock className="w-4 h-4" />}
                </div>

                {/* Details */}
                <div className="flex-1 pr-12">
                  <div className="flex items-center gap-2 mb-1">
                    <span
                      className={`inline-block rounded-full border px-2 py-0.5 text-[9px] font-semibold uppercase tracking-wider ${rarityBadge}`}
                    >
                      {ach.rarity}
                    </span>
                  </div>

                  <h3
                    className={`font-display text-sm font-bold tracking-wide ${
                      isUnlocked ? 'text-[#f5f0e6]' : 'text-stone-400'
                    }`}
                  >
                    {ach.title}
                  </h3>

                  <p className="mt-0.5 font-interface text-xs text-[#d6cbbe] leading-relaxed">
                    {ach.description}
                  </p>

                  {isUnlocked && unlockedAt && (
                    <div className="mt-2 flex items-center gap-1.5 text-[10px] text-[#e5c158]">
                      <CheckCircle2 className="w-3 h-3" />
                      <span>Unlocked on {new Date(unlockedAt).toLocaleDateString()}</span>
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
