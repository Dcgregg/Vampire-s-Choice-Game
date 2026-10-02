import React from 'react';
import { BookOpen, Check, Clock3, Play, LockKeyhole, MessageCircle } from 'lucide-react';
import { BOOKS, SERIES } from '../../data/story';
import { useGameState } from '../../state/useGameState';
import { getPublicPlayerCatalogue } from '../../sync/cloudClient';

export const LibraryScreen: React.FC = () => {
  const { state, continueStory } = useGameState();
  const [published, setPublished] = React.useState<string[]>([]);
  React.useEffect(() => { void getPublicPlayerCatalogue().then(({ books }) => setPublished(books.map((book) => book.bookId))).catch(() => setPublished([])); }, []);
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
          const previous = refs.find((candidate) => candidate.order === ref.order - 1);
          const unlocked = ref.order === 1 || (!!previous && state.progress.completedBooks.includes(previous.id));
          const hasPublishedReader = published.includes(ref.id);
          const playable = unlocked && hasPublishedReader;
          return (
            <section key={ref.id} className="rounded-xl border border-white/10 bg-[#150f1f] p-5">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-xs uppercase tracking-widest text-[#c5a059]">Book {ref.order}</p>
                  <h2 className="mt-1 font-display text-xl text-[#f5f0e6]">{loaded?.subtitle || loaded?.title || `Chronicle ${ref.order}`}</h2>
                </div>
                <span className="flex items-center gap-1 text-xs text-stone-400">
                  {complete ? <><Check className="h-4 w-4 text-emerald-400" /> Complete</> : !unlocked ? <><LockKeyhole className="h-4 w-4" /> Finish the previous book</> :
                    !hasPublishedReader && ref.status === 'coming_soon' ? <><Clock3 className="h-4 w-4" /> Coming soon</> :
                    hasPublishedReader ? <><BookOpen className="h-4 w-4" /> Ready to play</> : <><Clock3 className="h-4 w-4" /> Awaiting publication</>}
                </span>
              </div>
              {current && state.player && (
                <button onClick={continueStory} className="mt-4 flex items-center gap-2 rounded-lg border border-[#c5a059] px-4 py-2 text-sm text-[#f5f0e6]">
                  <Play className="h-4 w-4" /> {complete ? 'View completion' : 'Continue'}
                </button>
              )}
              {!current && playable && <a href={`/?publishedBook=${encodeURIComponent(ref.id)}`} className="mt-4 inline-flex items-center gap-2 rounded-lg border border-[#c5a059] px-4 py-2 text-sm text-[#f5f0e6]"><Play className="h-4 w-4" />Choose this next book</a>}
              {!unlocked && <p className="mt-3 text-xs text-stone-500">This chronicle unlocks when you finish {previous?.id === 'book1' ? 'Book I' : `Book ${previous?.order}`}.</p>}
            </section>
          );
        })}
      </div>
      <section className="mt-8 rounded-xl border border-violet-300/20 bg-gradient-to-br from-[#191126] to-[#100b17] p-5 opacity-90"><div className="flex items-start gap-3"><MessageCircle className="mt-1 h-5 w-5 text-violet-200"/><div><p className="text-xs font-semibold uppercase tracking-wider text-violet-200">Coming soon · Paid feature</p><h2 className="mt-1 font-display text-xl text-[#f5f0e6]">Talk with a character</h2><p className="mt-2 max-w-xl text-sm text-stone-400">Step into an AI roleplay conversation with characters from the story. This optional premium feature is in development.</p></div></div></section>
    </div>
  );
};
