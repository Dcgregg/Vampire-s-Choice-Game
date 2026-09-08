import React from 'react';
import { useGameState } from '../../state/useGameState';
import { Heart, Sparkles, Shield, UserCheck } from 'lucide-react';

export const RelationshipsScreen: React.FC = () => {
  const { state } = useGameState();
  const characters = Object.values(state.relationships);

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'Devoted':
        return 'text-rose-400 border-rose-900/60 bg-rose-950/40';
      case 'Trusted':
        return 'text-[#fae092] border-[#c5a059]/40 bg-[#251930]';
      case 'Intrigued':
        return 'text-purple-300 border-purple-900/40 bg-purple-950/30';
      case 'Rival':
        return 'text-amber-400 border-amber-900/40 bg-amber-950/30';
      case 'Acquaintance':
      default:
        return 'text-stone-300 border-white/10 bg-black/30';
    }
  };

  const getCharacterEmoji = (id: string) => {
    switch (id) {
      case 'lucian':
        return '🦇';
      case 'isolde':
        return '🧪';
      case 'nico':
        return '📜';
      case 'marcella':
        return '🕯️';
      default:
        return '👤';
    }
  };

  return (
    <div className="mx-auto max-w-lg px-4 py-6 pb-24 space-y-5">
      {/* Header */}
      <div className="text-center">
        <span className="text-[10px] uppercase tracking-widest text-[#e5c158] font-semibold">
          Nocturne Connections
        </span>
        <h2 className="font-display text-2xl font-bold text-[#f5f0e6] mt-1">
          Bonds & Affinities
        </h2>
        <p className="font-narrative italic text-xs text-[#d6cbbe] mt-1">
          "Trust is fragile among the immortals. A single glance may turn an elder into an ally... or a rival."
        </p>
      </div>

      {/* Characters List */}
      <div className="space-y-4">
        {characters.map((char) => {
          const emoji = getCharacterEmoji(char.id);
          const statusBadge = getStatusColor(char.status);

          return (
            <div
              key={char.id}
              className="relative rounded-2xl border border-[#2d1f38] bg-gradient-to-r from-[#170e22] to-[#110919] p-4 sm:p-5 shadow-lg transition hover:border-[#c5a059]/40"
            >
              {/* Top Row: Avatar, Name, Title, Affinity */}
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-3">
                  <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border border-[#c5a059]/40 bg-[#1f122b] text-2xl shadow-inner">
                    {emoji}
                  </div>
                  <div>
                    <h3 className="font-display text-sm sm:text-base font-bold text-[#f5f0e6]">
                      {char.name}
                    </h3>
                    <p className="font-interface text-[11px] text-[#c5a059]">{char.title}</p>
                  </div>
                </div>

                {/* Affinity Score */}
                <div className="text-right">
                  <div className="flex items-center justify-end gap-1.5 text-xs font-semibold text-rose-300">
                    <Heart className="w-3.5 h-3.5 fill-rose-600 text-rose-500 animate-pulse" />
                    <span className="font-display text-base text-white">{char.affinity}</span>
                  </div>
                  <span
                    className={`mt-1 inline-block rounded-full border px-2 py-0.5 text-[10px] font-medium tracking-wide ${statusBadge}`}
                  >
                    {char.status}
                  </span>
                </div>
              </div>

              {/* Affinity Progress Bar */}
              <div className="mt-3.5">
                <div className="flex justify-between text-[10px] text-stone-400 mb-1">
                  <span>Affinity</span>
                  <span>{char.affinity} / 100</span>
                </div>
                <div className="h-1.5 w-full rounded-full bg-black/60 overflow-hidden border border-white/5">
                  <div
                    className="h-full bg-gradient-to-r from-rose-800 via-rose-600 to-[#e5c158] transition-all duration-500 rounded-full"
                    style={{ width: `${char.affinity}%` }}
                  />
                </div>
              </div>

              {/* Bio Teaser */}
              <p className="mt-3 font-narrative text-xs text-[#d6cbbe] leading-relaxed italic border-t border-white/5 pt-2.5">
                {char.description}
              </p>

              {/* Unlocked Lore Badges */}
              {char.loreUnlocked.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {char.loreUnlocked.map((lore, lIdx) => (
                    <span
                      key={lIdx}
                      className="inline-flex items-center gap-1 rounded-md bg-black/40 border border-white/5 px-2 py-0.5 text-[10px] text-stone-300"
                    >
                      <Sparkles className="w-2.5 h-2.5 text-[#e5c158]" />
                      <span>{lore}</span>
                    </span>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
