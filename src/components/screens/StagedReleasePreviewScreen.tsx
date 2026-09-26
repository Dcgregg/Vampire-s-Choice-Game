import React from 'react';
import { FlaskConical } from 'lucide-react';
import { getStagedReleasePreview, StagedReleasePreview } from '../../sync/cloudClient';
import { DraftPlaytest } from './DraftPlaytest';

export const StagedReleasePreviewScreen: React.FC<{ bookId: string }> = ({ bookId }) => {
  const [preview, setPreview] = React.useState<StagedReleasePreview | null | undefined>(undefined);
  React.useEffect(() => { void getStagedReleasePreview(bookId).then(setPreview).catch(() => setPreview(null)); }, [bookId]);
  if (preview === undefined) return <div className="mx-auto max-w-3xl p-8 text-stone-400">Loading staged release…</div>;
  if (!preview) return <div className="mx-auto max-w-3xl p-8 text-center text-stone-300"><FlaskConical className="mx-auto h-8 w-8 text-sky-300" /><h1 className="mt-4 font-display text-2xl">No staged release available</h1><p className="mt-2 text-sm text-stone-400">Ask an administrator to stage a selected release for {bookId}, with the staging preview flag enabled.</p></div>;
  return <div className="mx-auto max-w-4xl p-6 sm:p-10"><header className="rounded-xl border border-sky-400/30 bg-sky-950/20 p-5"><p className="text-xs font-semibold uppercase tracking-wider text-sky-200">Staging release preview · version {preview.release.version}</p><h1 className="mt-2 font-display text-3xl text-[#f5f0e6]">{preview.snapshot.title}</h1><p className="mt-2 text-sm text-stone-300">This is frozen staging content. Choices and values are local to this browser; no player account or production save is changed.</p></header><DraftPlaytest draft={preview.snapshot} mode="staged" /></div>;
};
