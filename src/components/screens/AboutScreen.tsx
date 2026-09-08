import React from 'react';
import { useGameState } from '../../state/useGameState';
import { ArrowLeft, BookOpen, Heart, Sparkles, Layers, ShieldCheck } from 'lucide-react';

export const AboutScreen: React.FC = () => {
  const { setScreen } = useGameState();

  return (
    <div className="mx-auto max-w-lg px-4 py-6 pb-24 space-y-6">
      <button
        onClick={() => setScreen('landing')}
        className="flex items-center gap-1.5 text-xs text-stone-400 hover:text-white transition"
      >
        <ArrowLeft className="w-4 h-4" />
        <span>Back to Entrance</span>
      </button>

      {/* Header */}
      <div className="text-center">
        <span className="text-[10px] uppercase tracking-widest text-[#e5c158] font-semibold">
          About the Experience
        </span>
        <h2 className="font-display text-2xl sm:text-3xl font-bold text-[#f5f0e6] mt-1">
          Vampire's Choice
        </h2>
        <p className="font-narrative italic text-sm text-[#d6cbbe] mt-2">
          "Where every choice has a price."
        </p>
      </div>

      {/* Concept Pillars */}
      <div className="space-y-3">
        <div className="rounded-xl border border-white/10 bg-[#140e1c] p-4 flex items-start gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-[#c5a059]/40 bg-[#1d1226] text-[#fae092]">
            <BookOpen className="w-4 h-4" />
          </div>
          <div>
            <h4 className="font-display text-sm font-bold text-white">
              Branching Narrative RPG
            </h4>
            <p className="text-xs text-[#d6cbbe] mt-0.5 leading-relaxed">
              Every decision permanently alters story flags, character reactions, unlocked lore, and future dilemmas across Blackthorn Academy.
            </p>
          </div>
        </div>

        <div className="rounded-xl border border-white/10 bg-[#140e1c] p-4 flex items-start gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-rose-800/40 bg-rose-950/40 text-rose-300">
            <Heart className="w-4 h-4 fill-rose-600/40" />
          </div>
          <div>
            <h4 className="font-display text-sm font-bold text-white">
              Gothic Romance & Affinities
            </h4>
            <p className="text-xs text-[#d6cbbe] mt-0.5 leading-relaxed">
              Dynamic relationships with Lord Lucian Cross, Lady Isolde Vance, and Nicholas Drake develop based on emotional honesty, danger, and mutual respect.
            </p>
          </div>
        </div>

        <div className="rounded-xl border border-white/10 bg-[#140e1c] p-4 flex items-start gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-[#c5a059]/40 bg-[#1d1226] text-[#e5c158]">
            <Layers className="w-4 h-4" />
          </div>
          <div>
            <h4 className="font-display text-sm font-bold text-white">
              Clean, Decoupled Architecture
            </h4>
            <p className="text-xs text-[#d6cbbe] mt-0.5 leading-relaxed">
              Story data, game state, UI components, and local persistence are rigorously separated to allow seamless future export to GitHub and backend integration.
            </p>
          </div>
        </div>
      </div>

      {/* Return Button */}
      <button
        onClick={() => setScreen('landing')}
        className="w-full rounded-xl border border-[#c5a059] bg-gradient-to-r from-rose-950 via-rose-900 to-rose-950 py-3 font-display text-xs font-bold uppercase tracking-widest text-white shadow-lg transition hover:from-rose-900 hover:to-rose-800"
      >
        Return to Welcome
      </button>
    </div>
  );
};
