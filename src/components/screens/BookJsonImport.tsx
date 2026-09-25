import React from 'react';
import { FileUp } from 'lucide-react';
import { AdminDraft, importAdminBookJson } from '../../sync/cloudClient';

export const BookJsonImport: React.FC<{ onImported: (draft: AdminDraft) => void }> = ({ onImported }) => {
  const [working, setWorking] = React.useState(false);
  const [notice, setNotice] = React.useState<string | null>(null);
  const chooseFile = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    if (file.size > 480_000) { setNotice('Choose a JSON file smaller than 480 KB.'); return; }
    setWorking(true); setNotice(null);
    try {
      const content = JSON.parse(await file.text()) as Record<string, unknown>;
      onImported(await importAdminBookJson(content));
      setNotice('Imported as a private draft. Review, playtest and approve it before any future publication step.');
    } catch { setNotice('That file could not be validated as a complete Book JSON draft.'); }
    finally { setWorking(false); }
  };
  return <section className="mt-6 rounded-xl border border-white/10 bg-[#150f1f] p-5"><div className="flex items-start justify-between gap-4"><div><h2 className="flex items-center gap-2 font-display text-xl text-[#f5f0e6]"><FileUp className="h-5 w-5 text-[#e5c158]" />Import Book JSON</h2><p className="mt-1 text-sm text-stone-400">The file is validated and converted into a private draft. It cannot write to player content.</p></div><label className="cursor-pointer rounded border border-[#c5a059]/70 px-3 py-2 text-sm font-semibold text-[#e5c158]">{working ? 'Importing…' : 'Choose JSON'}<input disabled={working} type="file" accept="application/json,.json" className="sr-only" onChange={(event) => void chooseFile(event)} /></label></div>{notice && <p className="mt-3 text-sm text-[#e5c158]">{notice}</p>}</section>;
};
