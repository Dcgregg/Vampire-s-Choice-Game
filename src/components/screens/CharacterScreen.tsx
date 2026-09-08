import React from 'react';
import { useGameState } from '../../state/useGameState';
import { User, Flame, Droplet, BookOpen, Key, Compass, Shield, Award } from 'lucide-react';

export const CharacterScreen: React.FC = () => {
  const { state, setScreen } = useGameState();
  const player = state.player;

  if (!player) {
    return (
      <div className="flex min-h-[70vh] flex-col items-center justify-center p-6 text-center">
        <User className="h-12 w-12 text-stone-500 mb-3" />
        <h3 className="font-display text-lg text-[#f5f0e6]">No Protagonist Created</h3>
        <p className="mt-1 text-xs text-stone-400">Step into the shadows to create your character.</p>
        <button
          onClick={() => setScreen('character_creation')}
          className="mt-4 rounded-xl border border-[#c5a059] bg-rose-950 px-5 py-2.5 text-xs font-semibold text-white shadow-lg"
        >
          Create Protagonist
        </button>
      </div>
    );
  }

  // Count active flags
  const flagsCount = Object.keys(state.flags).length;
  const achievementsCount = Object.values(state.achievements).filter((a) => a.unlockedAt).length;

  return (
    <div className="mx-auto max-w-lg px-4 py-6 pb-24 space-y-5">
      {/* Dossier Header */}
      <div className="relative rounded-2xl border border-[#c5a059]/40 bg-gradient-to-b from-[#180f24] to-[#0f0917] p-6 shadow-xl text-center">
        {/* Ornate Corner Pins */}
        <div className="absolute top-2 left-2 h-3 w-3 border-t border-l border-[#c5a059]/70" />
        <div className="absolute top-2 right-2 h-3 w-3 border-t border-r border-[#c5a059]/70" />
        <div className="absolute bottom-2 left-2 h-3 w-3 border-b border-l border-[#c5a059]/70" />
        <div className="absolute bottom-2 right-2 h-3 w-3 border-b border-r border-[#c5a059]/70" />

        <div className="mx-auto mb-3 flex h-16 w-16 items-center justify-center rounded-full border-2 border-[#c5a059] bg-[#12081c] text-3xl shadow-md">
          🦇
        </div>

        <span className="font-interface text-[10px] font-bold uppercase tracking-widest text-[#e5c158]">
          Blackthorn Scholar Dossier
        </span>
        <h2 className="font-display text-2xl font-bold text-[#f5f0e6] mt-1 tracking-wide">
          {player.name}
        </h2>
        <p className="font-narrative italic text-xs text-[#d6cbbe] mt-0.5">
          {player.genderIdentity} • {player.sexualOrientation}
        </p>

        {/* Currency & Streak Stats */}
        <div className="mt-5 grid grid-cols-2 gap-3 border-t border-white/5 pt-4">
          <div className="rounded-xl border border-rose-900/40 bg-rose-950/20 p-2.5">
            <div className="flex items-center justify-center gap-1.5 text-xs text-rose-300">
              <Droplet className="w-3.5 h-3.5 fill-rose-600 text-rose-500" />
              <span className="font-semibold text-white">{state.bloodCoins}</span>
            </div>
            <span className="text-[10px] text-stone-400 mt-0.5 block">Blood Coins</span>
          </div>

          <div className="rounded-xl border border-amber-900/40 bg-amber-950/20 p-2.5">
            <div className="flex items-center justify-center gap-1.5 text-xs text-amber-300">
              <Flame className="w-3.5 h-3.5 fill-amber-500 text-amber-400" />
              <span className="font-semibold text-white">{state.dailyStreak} Days</span>
            </div>
            <span className="text-[10px] text-stone-400 mt-0.5 block">Login Streak</span>
          </div>
        </div>
      </div>

      {/* Narrative Progress */}
      <div className="rounded-xl border border-white/10 bg-[#120a1a] p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-[#fae092]">
            <BookOpen className="w-4 h-4" />
            <span>Story Placement</span>
          </div>
          <button
            onClick={() => setScreen('reading')}
            className="text-xs text-rose-400 hover:text-rose-300 font-medium"
          >
            Resume Story →
          </button>
        </div>

        <div className="rounded-lg bg-black/40 p-3 border border-white/5 space-y-1">
          <div className="flex justify-between text-xs text-stone-300">
            <span>Book</span>
            <span className="font-medium text-white">I: Bloodlines of Blackthorn</span>
          </div>
          <div className="flex justify-between text-xs text-stone-300">
            <span>Active Chapter</span>
            <span className="font-medium text-[#fae092]">Chapter {state.progress.currentChapter}</span>
          </div>
          <div className="flex justify-between text-xs text-stone-300">
            <span>Scenes Traversed</span>
            <span className="font-medium text-white">{state.progress.sceneHistory.length}</span>
          </div>
        </div>
      </div>

      {/* Discovered Secrets & Inventory */}
      <div className="rounded-xl border border-white/10 bg-[#120a1a] p-4 space-y-3">
        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-[#fae092]">
          <Key className="w-4 h-4" />
          <span>Discovered Relics & Lore</span>
        </div>

        <div className="space-y-2">
          {state.flags.hasSilverKey && (
            <div className="flex items-center gap-2.5 rounded-lg border border-white/5 bg-black/40 p-2.5 text-xs text-[#ede5d8]">
              <span className="text-base">🗝️</span>
              <div>
                <span className="font-semibold text-white block">Antique Silver Key</span>
                <span className="text-[11px] text-stone-400">Found on the forbidden Scriptorium lectern.</span>
              </div>
            </div>
          )}

          {state.flags.acceptedSignet && (
            <div className="flex items-center gap-2.5 rounded-lg border border-white/5 bg-black/40 p-2.5 text-xs text-[#ede5d8]">
              <span className="text-base">💍</span>
              <div>
                <span className="font-semibold text-white block">House of Cross Signet</span>
                <span className="text-[11px] text-stone-400">Onyx raven with ruby eyes given by Lord Lucian.</span>
              </div>
            </div>
          )}

          {state.flags.hasPoisonVial && (
            <div className="flex items-center gap-2.5 rounded-lg border border-white/5 bg-black/40 p-2.5 text-xs text-[#ede5d8]">
              <span className="text-base">🧪</span>
              <div>
                <span className="font-semibold text-white block">Tainted Draught Vial</span>
                <span className="text-[11px] text-stone-400">Wolfsbane evidence recovered from the masquerade.</span>
              </div>
            </div>
          )}

          {!state.flags.hasSilverKey && !state.flags.acceptedSignet && !state.flags.hasPoisonVial && (
            <p className="text-xs italic text-stone-500 py-2">
              No relics discovered yet. Explore choices in the story to uncover artifacts.
            </p>
          )}
        </div>
      </div>

      {/* Record summary */}
      <div className="flex items-center justify-between text-xs text-stone-500 px-1">
        <span>Story Flags Registered: {flagsCount}</span>
        <span>Trophies Unlocked: {achievementsCount}/6</span>
      </div>
    </div>
  );
};
