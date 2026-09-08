import React from 'react';
import { useGameState } from '../../state/useGameState';
import { PWAInstallButton } from './PWAInstallButton';
import { Volume2, VolumeX, Flame, Droplet } from 'lucide-react';

export const Navbar: React.FC = () => {
  const { state, updateSettings, activeScreen, setScreen } = useGameState();

  const toggleSound = () => {
    updateSettings({ ambientAudio: !state.settings.ambientAudio });
  };

  return (
    <header className="sticky top-0 z-40 w-full border-b border-[#2a1e35]/60 bg-[#09070c]/90 backdrop-blur-md">
      <div className="mx-auto flex h-14 max-w-4xl items-center justify-between px-3 sm:px-6">
        {/* Brand / Title or Back */}
        <div className="flex items-center gap-2.5">
          <button
            id="nav-brand-btn"
            onClick={() => setScreen('landing')}
            className="group flex items-center gap-2 text-left focus:outline-none"
            title="Return to Welcome"
          >
            <div className="flex h-7 w-7 items-center justify-center rounded-lg border border-[#c5a059]/40 bg-[#170e20] shadow-sm transition group-hover:border-[#c5a059]">
              <span className="text-xs">🦇</span>
            </div>
            <div className="hidden xs:block">
              <span className="font-display text-xs font-semibold tracking-wider text-[#f5f0e6] group-hover:text-[#fae092] transition">
                VAMPIRE'S CHOICE
              </span>
            </div>
          </button>
        </div>

        {/* Right Status Controls: Currency, Streak, Audio, PWA */}
        <div className="flex items-center gap-2 sm:gap-3">
          {/* Blood Coins */}
          <div
            id="blood-coins-badge"
            className="flex items-center gap-1.5 rounded-full border border-rose-900/40 bg-rose-950/40 px-2.5 py-1 text-xs text-rose-200"
            title="Blood Coins — Earned through discovery and chapter completion"
          >
            <Droplet className="h-3.5 w-3.5 fill-rose-600 text-rose-500 animate-pulse" />
            <span className="font-interface font-semibold text-rose-100">{state.bloodCoins}</span>
          </div>

          {/* Daily Streak */}
          <div
            id="daily-streak-badge"
            className="flex items-center gap-1.5 rounded-full border border-amber-900/40 bg-amber-950/30 px-2.5 py-1 text-xs text-amber-200"
            title="Daily Login Streak"
          >
            <Flame className="h-3.5 w-3.5 fill-amber-500 text-amber-400" />
            <span className="font-interface font-medium">{state.dailyStreak}d</span>
          </div>

          {/* Ambient Sound Toggle */}
          <button
            id="audio-toggle-btn"
            onClick={toggleSound}
            className={`flex h-8 w-8 items-center justify-center rounded-full border transition-all ${
              state.settings.ambientAudio
                ? 'border-[#c5a059] bg-[#22162e] text-[#fae092] shadow-sm'
                : 'border-white/10 bg-black/40 text-stone-400 hover:text-stone-200'
            }`}
            title={state.settings.ambientAudio ? 'Mute Gothic Ambience' : 'Play Candlelit Ambience'}
          >
            {state.settings.ambientAudio ? (
              <Volume2 className="h-3.5 w-3.5 animate-pulse" />
            ) : (
              <VolumeX className="h-3.5 w-3.5" />
            )}
          </button>

          {/* In-app PWA install button */}
          <div className="hidden sm:block">
            <PWAInstallButton compact />
          </div>
        </div>
      </div>
    </header>
  );
};
