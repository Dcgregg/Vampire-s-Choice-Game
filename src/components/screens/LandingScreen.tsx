import React from 'react';
import { useGameState } from '../../state/useGameState';
import { BookOpen, Sparkles, Play, Info, Flame, Droplet, Library } from 'lucide-react';
import { PWAInstallButton } from '../common/PWAInstallButton';

export const LandingScreen: React.FC = () => {
  const { state, setScreen, continueStory } = useGameState();
  const hasExistingSave = Boolean(state.player && state.progress.currentSceneId);

  return (
    <div className="relative min-h-[calc(100vh-3.5rem)] flex flex-col justify-between items-center px-4 py-8 sm:py-12 overflow-hidden">
      {/* Background Gothic Vignette & Subtle Crimson Fog Glow */}
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-[#2a132e]/40 via-[#0a070e] to-[#040306]" />
      
      {/* Subtle Moonlit & Candle Ambient Glow */}
      <div className="pointer-events-none absolute -top-24 left-1/2 h-96 w-96 -translate-x-1/2 rounded-full bg-rose-950/20 blur-3xl" />
      <div className="pointer-events-none absolute top-1/3 left-1/4 h-64 w-64 rounded-full bg-[#c5a059]/10 blur-3xl" />

      {/* Top Banner with PWA and Prototype Status */}
      <div className="relative z-10 w-full max-w-md flex items-center justify-between text-xs text-stone-400">
        <div className="flex items-center gap-2">
          <span className="inline-block h-2 w-2 rounded-full bg-rose-600 animate-pulse" />
          <span className="font-interface font-medium tracking-wide uppercase text-stone-300">
            Step 1 • UX Prototype
          </span>
        </div>
        <PWAInstallButton compact />
      </div>

      {/* Center Branding & Hero */}
      <div className="relative z-10 my-auto flex flex-col items-center text-center max-w-lg">
        {/* Gothic Crest Icon */}
        <div className="mb-6 relative group">
          <div className="absolute -inset-2 rounded-full bg-gradient-to-r from-rose-900/40 via-[#c5a059]/30 to-rose-900/40 blur-md opacity-75 group-hover:opacity-100 transition duration-1000" />
          <div className="relative flex h-20 w-20 items-center justify-center rounded-full border-2 border-[#c5a059]/60 bg-[#120a1a] shadow-[0_0_25px_rgba(197,160,89,0.25)]">
            <span className="text-3xl filter drop-shadow-[0_2px_8px_rgba(225,29,72,0.8)]">🦇</span>
          </div>
        </div>

        {/* Title */}
        <h1 className="font-display text-3xl sm:text-4xl md:text-5xl font-extrabold tracking-wider text-[#f5f0e6] drop-shadow-md">
          VAMPIRE'S CHOICE
        </h1>

        {/* Decorative Divider */}
        <div className="my-4 flex items-center justify-center gap-3 w-48 opacity-80">
          <div className="h-[1px] flex-1 bg-gradient-to-r from-transparent to-[#c5a059]" />
          <div className="rotate-45 w-2 h-2 border border-[#c5a059] bg-rose-950" />
          <div className="h-[1px] flex-1 bg-gradient-to-l from-transparent to-[#c5a059]" />
        </div>

        {/* Tagline */}
        <p className="font-narrative italic text-lg sm:text-xl text-[#d8cfc4] tracking-wide max-w-xs sm:max-w-sm">
          "Every choice has a price."
        </p>

        {/* Synopsis teaser */}
        <p className="mt-4 font-interface text-xs sm:text-sm text-stone-400 max-w-md leading-relaxed">
          An interactive gothic-fantasy romance adventure. Step through the mist of Blackthorn Academy where ancient vampires, forbidden runes, and mortal alliances intertwine.
        </p>

        {/* Quick status preview if player exists */}
        {hasExistingSave && (
          <div className="mt-5 rounded-lg border border-white/10 bg-[#150f1f]/80 px-4 py-2.5 text-left text-xs text-stone-300 shadow-sm flex items-center justify-between gap-4 w-full max-w-sm">
            <div>
              <span className="text-[10px] uppercase font-semibold text-[#e5c158] block">Current Progress</span>
              <p className="font-medium text-[#f5f0e6]">
                {state.player?.name} • Chapter {state.progress.currentChapter}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <span className="flex items-center gap-1 text-rose-300"><Droplet className="w-3 h-3 fill-rose-600 text-rose-600" /> {state.bloodCoins}</span>
              <span className="flex items-center gap-1 text-amber-300"><Flame className="w-3 h-3 fill-amber-500 text-amber-500" /> {state.dailyStreak}d</span>
            </div>
          </div>
        )}

        {/* Action Buttons */}
        <div className="mt-8 flex flex-col gap-3 w-full max-w-xs">
          {hasExistingSave ? (
            <>
              <button
                id="landing-continue-btn"
                onClick={continueStory}
                className="group relative flex items-center justify-center gap-2.5 rounded-xl border border-[#c5a059] bg-gradient-to-r from-rose-950 via-rose-900 to-rose-950 px-6 py-3.5 font-display text-sm font-bold uppercase tracking-widest text-[#f5f0e6] shadow-[0_4px_20px_rgba(190,18,60,0.35)] transition-all duration-300 hover:scale-[1.02] hover:shadow-[0_4px_25px_rgba(190,18,60,0.55)] active:scale-[0.98]"
              >
                <Play className="h-4 w-4 fill-current text-[#fae092]" />
                <span>Continue Story</span>
              </button>

              <button
                id="landing-library-btn"
                onClick={() => setScreen('library')}
                className="flex items-center justify-center gap-2 rounded-xl border border-white/10 bg-[#120a1a]/80 px-6 py-3 font-interface text-xs font-semibold uppercase tracking-wider text-[#d6cbbe]"
              >
                <Library className="h-3.5 w-3.5 text-[#e5c158]" />
                <span>Story Library</span>
              </button>

              <button
                id="landing-new-story-btn"
                onClick={() => setScreen('character_creation')}
                className="flex items-center justify-center gap-2 rounded-xl border border-white/10 bg-[#120a1a]/80 px-6 py-3 font-interface text-xs font-semibold uppercase tracking-wider text-[#d6cbbe] transition hover:border-[#c5a059]/50 hover:bg-[#1a0f26] active:scale-[0.98]"
              >
                <Sparkles className="h-3.5 w-3.5 text-[#e5c158]" />
                <span>New Character / Restart</span>
              </button>
            </>
          ) : (
            <button
              id="landing-begin-btn"
              onClick={() => setScreen('character_creation')}
              className="group relative flex items-center justify-center gap-2.5 rounded-xl border border-[#c5a059] bg-gradient-to-r from-rose-950 via-rose-900 to-rose-950 px-6 py-3.5 font-display text-sm font-bold uppercase tracking-widest text-[#f5f0e6] shadow-[0_4px_20px_rgba(190,18,60,0.4)] transition-all duration-300 hover:scale-[1.02] hover:shadow-[0_4px_25px_rgba(190,18,60,0.6)] active:scale-[0.98]"
            >
              <BookOpen className="h-4 w-4 text-[#fae092]" />
              <span>Begin Your Story</span>
            </button>
          )}

          <button
            id="landing-about-btn"
            onClick={() => setScreen('about')}
            className="flex items-center justify-center gap-2 rounded-xl border border-white/5 bg-transparent px-4 py-2 font-interface text-xs text-stone-400 transition hover:text-stone-200"
          >
            <Info className="h-3.5 w-3.5" />
            <span>About Vampire's Choice</span>
          </button>
        </div>
      </div>

      {/* Footer Info */}
      <footer className="relative z-10 mt-6 text-center text-[11px] text-stone-500">
        <p>© Vampire's Choice • Mobile-First CYOA Gothic Romance Engine</p>
      </footer>
    </div>
  );
};
