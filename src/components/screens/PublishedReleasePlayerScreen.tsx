import React from 'react';
import { BookOpen, RotateCcw, ShieldCheck } from 'lucide-react';

type Choice = { id: string; text: string; nextSceneId?: string; endsBook?: boolean };
type Scene = { id: string; chapterNumber: number; sceneTitle: string; paragraphs: string[]; dialogues?: Array<{ speaker: string; text: string; mood?: string }>; choices: Choice[] };
type Bundle = { book: { title: string; subtitle?: string; version: number; startingSceneId: string }; scenes: Scene[] };
type PublicRelease = { published: { releaseVersion: number; checksum: string }; playerBundle: Bundle };

const getPublishedBook = async (bookId: string): Promise<PublicRelease> => {
  const response = await fetch(`/api/player/catalogue/${encodeURIComponent(bookId)}`);
  if (!response.ok) throw new Error('published_book_not_found');
  return response.json() as Promise<PublicRelease>;
};

export const PublishedReleasePlayerScreen: React.FC<{ bookId: string }> = ({ bookId }) => {
  const [release, setRelease] = React.useState<PublicRelease | null | undefined>(undefined);
  const [sceneId, setSceneId] = React.useState<string | null>(null);
  React.useEffect(() => { void getPublishedBook(bookId).then((next) => { setRelease(next); setSceneId(next.playerBundle.book.startingSceneId); }).catch(() => setRelease(null)); }, [bookId]);
  if (release === undefined) return <div className="mx-auto max-w-3xl p-10 text-center text-stone-400">Loading published story…</div>;
  if (!release) return <div className="mx-auto max-w-3xl p-10 text-center text-stone-300"><BookOpen className="mx-auto h-8 w-8 text-[#c5a059]" /><h1 className="mt-4 font-display text-2xl">This story is not currently available</h1><p className="mt-2 text-sm text-stone-400">It may have been unpublished or rolled back.</p><a className="mt-5 inline-block rounded border border-[#c5a059]/60 px-4 py-2 text-sm text-[#e5c158]" href="/">Return home</a></div>;
  const bundle = release.playerBundle;
  const scene = bundle.scenes.find((item) => item.id === sceneId);
  const restart = () => setSceneId(bundle.book.startingSceneId);
  return <div className="mx-auto max-w-4xl p-6 sm:p-10"><header className="rounded-xl border border-emerald-400/30 bg-emerald-950/20 p-5"><p className="text-xs font-semibold uppercase tracking-wider text-emerald-200">Published story · release v{release.published.releaseVersion}</p><h1 className="mt-2 font-display text-3xl text-[#f5f0e6]">{bundle.book.title}</h1><p className="mt-2 text-sm text-stone-300">An immutable, version-pinned release. Your existing account progress is kept separate.</p></header><section className="mt-6 rounded-xl border border-[#c5a059]/30 bg-[#150f1f] p-5"><div className="flex items-center justify-between gap-3"><p className="flex items-center gap-2 text-sm text-emerald-100"><ShieldCheck className="h-4 w-4" />Published player edition</p><button onClick={restart} className="text-sm text-stone-200"><RotateCcw className="inline h-4 w-4" /> Restart</button></div>{!scene ? <div className="mt-6 rounded border border-emerald-400/30 bg-emerald-950/20 p-5"><h2 className="font-display text-2xl text-emerald-100">End of this release</h2><p className="mt-2 text-sm text-stone-300">Thank you for reading.</p></div> : <article className="mt-5"><p className="text-xs font-semibold uppercase tracking-wider text-[#c5a059]">Chapter {scene.chapterNumber}</p><h2 className="mt-2 font-display text-2xl text-[#f5f0e6]">{scene.sceneTitle}</h2>{scene.paragraphs.map((paragraph, index) => <p key={index} className="mt-4 whitespace-pre-wrap text-stone-200">{paragraph}</p>)}{scene.dialogues?.map((line, index) => <div key={index} className="mt-3 rounded bg-[#25182d] p-3"><strong className="text-[#e5c158]">{line.speaker}</strong><p className="mt-1 text-sm text-stone-100">{line.text}</p></div>)}<div className="mt-5 grid gap-2">{scene.choices.map((choice) => <button key={choice.id} onClick={() => setSceneId(choice.nextSceneId ?? null)} className="rounded border border-[#c5a059]/40 p-3 text-left font-semibold text-[#f5f0e6]">{choice.text}</button>)}</div></article>}<p className="mt-5 text-xs text-stone-500">Release checksum: {release.published.checksum.slice(0, 12)}… · This public edition does not overwrite account saves.</p></section></div>;
};
