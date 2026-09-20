import React from 'react';
import { ShieldCheck, BookOpen, LockKeyhole } from 'lucide-react';
import { AdminCatalog, getAdminCatalog } from '../../sync/cloudClient';

export const AdminScreen: React.FC = () => {
  const [catalog, setCatalog] = React.useState<AdminCatalog | null | undefined>(undefined);
  React.useEffect(() => { void getAdminCatalog().then(setCatalog).catch(() => setCatalog(null)); }, []);
  if (catalog === undefined) return <div className="p-8 text-stone-400">Loading admin catalogue…</div>;
  if (!catalog) return <div className="mx-auto max-w-md p-10 text-center text-stone-300"><LockKeyhole className="mx-auto h-8 w-8 text-rose-300" /><h1 className="mt-4 font-display text-2xl">Admin access required</h1><p className="mt-2 text-sm text-stone-400">Sign in with an allow-listed administrator account.</p></div>;
  return <div className="mx-auto max-w-2xl p-6 sm:p-10"><div className="flex items-center gap-3"><ShieldCheck className="h-7 w-7 text-[#e5c158]" /><div><h1 className="font-display text-3xl text-[#f5f0e6]">Story Admin</h1><p className="text-sm text-stone-400">Read-only catalogue — editing and publishing are not enabled yet.</p></div></div><div className="mt-8 grid gap-3">{catalog.series.sort((a,b) => a.order-b.order).map((ref) => { const book = catalog.books.find((entry) => entry.id === ref.id); return <article key={ref.id} className="rounded-xl border border-white/10 bg-[#150f1f] p-4"><div className="flex items-center justify-between"><div className="flex items-center gap-2"><BookOpen className="h-4 w-4 text-[#c5a059]" /><strong className="text-[#f5f0e6]">Book {ref.order}: {ref.id}</strong></div><span className="text-xs uppercase text-stone-400">{ref.status}</span></div><p className="mt-2 text-sm text-stone-400">{book ? `${book.sceneCount} scenes · content v${book.version}` : 'No bundled content yet'}</p></article>; })}</div></div>;
};
