import React from 'react';
import { BookOpen, Check, Clock3, Play } from 'lucide-react';
import { BOOKS, SERIES } from '../../data/story';
import { useGameState } from '../../state/useGameState';

export const LibraryScreen: React.FC = () => {
  const { state, continueStory } = useGameState();
  const refs = [...SERIES.books].sort((a, b) => a.order - b.order);
  return (
    <div className="mx-auto min-h-[calc(100vh-3.5rem)] w-full max-w-2xl px-4 py-10">
      <h1 className="font-display text-3xl font-bold text-[#f5f0e6]">Story Library</h1>
      <p className="mt-2 text-sm text-stone-400">Your chronicles and the stories still to come.</p>
      <div className="mt-8 grid gap-4">
        {refs.map((ref) => {
          const loaded = BOOKS[ref.id];
          const complete = state.progress.completedBooks.includes(ref.id);
          const current = state.progress.currentBookId === ref.id;
          return (
            <section key={ref.id} className="rounded-xl border border-white/10 bg-[#150f1f] p-5">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-xs uppercase tracking-widest text-[#c5a059]">Book {ref.order}</p>
                  <h2 className="mt-1 font-display text-xl text-[#f5f0e6]">{loaded?.subtitle || loaded?.title || `Chronicle ${ref.order}`}</h2>
                </div>
                <span className="flex items-center gap-1 text-xs text-stone-400">
                  {complete ? <><Check className="h-4 w-4 text-emerald-400" /> Complete</> :
                    ref.status === 'coming_soon' ? <><Clock3 className="h-4 w-4" /> Coming soon</> :
                    <><BookOpen className="h-4 w-4" /> Available</>}
                </span>
              </div>
              {current && state.player && (
                <button onClick={continueStory} className="mt-4 flex items-center gap-2 rounded-lg border border-[#c5a059] px-4 py-2 text-sm text-[#f5f0e6]">
                  <Play className="h-4 w-4" /> {complete ? 'View completion' : 'Continue'}
                </button>
              )}
            </section>
          );
        })}
      </div>
    </div>
  );
};
