import React from 'react';
import { useGameState } from '../../state/useGameState';
import { BOOKS, SERIES } from '../../data/story';
import { Crown, BookMarked, Check, Heart, Trophy, Library, Sparkles } from 'lucide-react';

export const BookCompleteScreen: React.FC = () => {
  const { state, setScreen } = useGameState();

  const bookId = state.progress.currentBookId;
  const book = BOOKS[bookId];
  const bookTitle = book?.subtitle || book?.title || 'Book I';

  const unlockedCount = Object.values(state.achievements).filter((a) => a.unlockedAt).length;
  const totalCount = Object.values(state.achievements).length;

  // Highest-affinity bond for a small, no-frills summary line.
  const topBond = Object.values(state.relationships)
    .slice()
    .sort((a, b) => b.affinity - a.affinity)[0];

  const nextBook = SERIES.books.find((b) => b.status === 'coming_soon');

  return (
    <div
      data-testid="book-complete-screen"
      className="relative min-h-[calc(100vh-3.5rem)] flex flex-col items-center px-4 py-10 overflow-hidden"
    >
      {/* Ambient gothic glow */}
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-[#2a132e]/50 via-[#0a070e] to-[#040306]" />
      <div className="pointer-events-none absolute -top-24 left-1/2 h-96 w-96 -translate-x-1/2 rounded-full bg-rose-950/25 blur-3xl" />
      <div className="pointer-events-none absolute top-1/3 right-1/4 h-64 w-64 rounded-full bg-[#c5a059]/10 blur-3xl" />

      <div className="relative z-10 my-auto flex w-full max-w-md flex-col items-center text-center">
        {/* Crest */}
        <div className="mb-6 relative">
          <div className="absolute -inset-2 rounded-full bg-gradient-to-r from-rose-900/40 via-[#c5a059]/30 to-rose-900/40 blur-md opacity-80" />
          <div className="relative flex h-20 w-20 items-center justify-center rounded-full border-2 border-[#c5a059]/60 bg-[#120a1a] shadow-[0_0_25px_rgba(197,160,89,0.3)]">
            <Crown className="h-9 w-9 text-[#fae092]" />
          </div>
        </div>

        <p className="font-interface text-[11px] font-semibold uppercase tracking-[0.3em] text-[#e5c158]">
          Chronicle Complete
        </p>
        <h1 className="mt-3 font-display text-3xl sm:text-4xl font-extrabold tracking-wide text-[#f5f0e6] drop-shadow-md">
          {bookTitle}
        </h1>

        <div className="my-4 flex items-center justify-center gap-3 w-48 opacity-80">
          <div className="h-[1px] flex-1 bg-gradient-to-r from-transparent to-[#c5a059]" />
          <div className="rotate-45 w-2 h-2 border border-[#c5a059] bg-rose-950" />
          <div className="h-[1px] flex-1 bg-gradient-to-l from-transparent to-[#c5a059]" />
        </div>

        <p className="font-narrative italic text-lg text-[#d8cfc4] max-w-sm">
          The final candle gutters. Your first tale within the walls of Blackthorn is written in blood and memory.
        </p>

        {/* Saved confirmation */}
        <div
          data-testid="book-complete-saved-note"
          className="mt-6 flex items-center gap-2 rounded-full border border-emerald-800/40 bg-emerald-950/30 px-4 py-1.5 text-xs font-medium text-emerald-300"
        >
          <Check className="h-3.5 w-3.5" />
          <span>Your progress has been saved</span>
        </div>

        {/* Small summary from existing data */}
        <div className="mt-6 grid w-full grid-cols-2 gap-3">
          <div className="rounded-xl border border-[#332244]/80 bg-[#150f1f]/80 px-4 py-3 text-left">
            <div className="flex items-center gap-2 text-[#e5c158]">
              <Trophy className="h-4 w-4" />
              <span className="font-interface text-[10px] font-semibold uppercase tracking-wider">Achievements</span>
            </div>
            <p className="mt-1 font-display text-xl font-bold text-[#f5f0e6]">
              {unlockedCount}<span className="text-sm text-stone-400"> / {totalCount}</span>
            </p>
          </div>
          <div className="rounded-xl border border-[#332244]/80 bg-[#150f1f]/80 px-4 py-3 text-left">
            <div className="flex items-center gap-2 text-rose-300">
              <Heart className="h-4 w-4" />
              <span className="font-interface text-[10px] font-semibold uppercase tracking-wider">Closest Bond</span>
            </div>
            <p className="mt-1 font-display text-base font-bold text-[#f5f0e6] truncate">
              {topBond ? topBond.name.split(' ').slice(-1)[0] : '—'}
            </p>
            <p className="text-[11px] text-stone-400">{topBond ? topBond.status : ''}</p>
          </div>
        </div>

        {/* Book II teaser */}
        {nextBook && (
          <div
            data-testid="book-complete-next-teaser"
            className="mt-6 flex items-center gap-3 rounded-xl border border-white/10 bg-[#100a18]/80 px-4 py-3 text-left w-full"
          >
            <BookMarked className="h-5 w-5 shrink-0 text-[#c5a059]" />
            <div>
              <p className="font-display text-sm font-semibold text-[#f5f0e6]">Book II: The Crimson Throne</p>
              <p className="font-interface text-[11px] text-stone-400">
                Not yet available — the next chronicle is still being written.
              </p>
            </div>
          </div>
        )}

        {/* Return to library */}
        <button
          data-testid="book-complete-return-btn"
          id="book-complete-return-btn"
          onClick={() => setScreen('landing')}
          className="group mt-8 flex w-full max-w-xs items-center justify-center gap-2.5 rounded-xl border border-[#c5a059] bg-gradient-to-r from-rose-950 via-rose-900 to-rose-950 px-6 py-3.5 font-display text-sm font-bold uppercase tracking-widest text-[#f5f0e6] shadow-[0_4px_20px_rgba(190,18,60,0.35)] transition-all duration-300 hover:scale-[1.02] hover:shadow-[0_4px_25px_rgba(190,18,60,0.55)] active:scale-[0.98]"
        >
          <Library className="h-4 w-4 text-[#fae092]" />
          <span>Return to the Library</span>
        </button>

        <p className="mt-4 flex items-center gap-1.5 font-interface text-[11px] text-stone-500">
          <Sparkles className="h-3 w-3 text-[#c5a059]" />
          Your relationships, flags and achievements carry forward into future books.
        </p>
      </div>
    </div>
  );
};
