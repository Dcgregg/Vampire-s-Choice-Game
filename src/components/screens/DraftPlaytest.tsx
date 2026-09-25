import React from 'react';
import { Eye, RotateCcw } from 'lucide-react';
import { AdminDraft, AdminScene } from '../../sync/cloudClient';

const firstScene = (scenes: AdminScene[]) => [...scenes].sort((a, b) => a.chapterNumber - b.chapterNumber)[0] ?? null;

export const DraftPlaytest: React.FC<{ draft: AdminDraft }> = ({ draft }) => {
  const scenes = draft.scenes ?? [];
  const scenesById = React.useMemo(() => new Map(scenes.map((scene) => [scene.sceneId, scene])), [scenes]);
  const [sceneId, setSceneId] = React.useState<string | null>(() => firstScene(scenes)?.sceneId ?? null);
  const [history, setHistory] = React.useState<string[]>([]);

  React.useEffect(() => { setSceneId(firstScene(scenes)?.sceneId ?? null); setHistory([]); }, [draft.draftId, draft.revision]);
  const scene = sceneId ? scenesById.get(sceneId) ?? null : null;
  const restart = () => { setSceneId(firstScene(scenes)?.sceneId ?? null); setHistory([]); };
  const choose = (nextSceneId?: string | null) => {
    if (!scene) return;
    setHistory((items) => [...items, scene.sceneId]);
    setSceneId(nextSceneId || null);
  };

  return <section className="mt-6 rounded-xl border border-[#c5a059]/30 bg-[#150f1f] p-5"><div className="flex items-start justify-between gap-4"><div><h2 className="flex items-center gap-2 font-display text-xl text-[#f5f0e6]"><Eye className="h-5 w-5 text-[#e5c158]" />Draft playtest</h2><p className="mt-1 text-sm text-stone-400">Private preview only — no progress, player data or live story content is changed.</p></div><button onClick={restart} className="inline-flex items-center gap-1 rounded border border-white/15 px-3 py-2 text-sm text-stone-200"><RotateCcw className="h-4 w-4" />Restart</button></div>{scenes.length === 0 ? <p className="mt-5 rounded border border-dashed border-white/15 p-4 text-sm text-stone-400">Add and save at least one scene to begin a playtest.</p> : !scene ? <div className="mt-5 rounded border border-white/15 bg-black/15 p-5"><h3 className="font-display text-xl text-[#f5f0e6]">End of this route</h3><p className="mt-2 text-sm text-stone-400">This choice has no destination scene yet.</p></div> : <div className="mt-5 rounded border border-white/10 bg-black/15 p-5"><p className="text-xs font-semibold uppercase tracking-wider text-[#c5a059]">Chapter {scene.chapterNumber}</p><h3 className="mt-2 font-display text-2xl text-[#f5f0e6]">{scene.title}</h3><div className="mt-5 whitespace-pre-wrap leading-7 text-stone-200">{scene.body}</div><div className="mt-6 grid gap-3">{scene.choices.length === 0 ? <p className="text-sm text-stone-400">This scene has no choices yet.</p> : scene.choices.map((choice) => { const missingTarget = Boolean(choice.nextSceneId && !scenesById.has(choice.nextSceneId)); return <button key={choice.choiceId} disabled={missingTarget} onClick={() => choose(choice.nextSceneId)} className="rounded-lg border border-[#c5a059]/40 bg-[#25182d] px-4 py-3 text-left text-sm text-[#f5f0e6] transition hover:border-[#e5c158] disabled:cursor-not-allowed disabled:opacity-50"><span className="block font-semibold">{choice.text}</span>{missingTarget && <span className="mt-1 block text-xs text-rose-300">Destination scene “{choice.nextSceneId}” has not been written yet.</span>}</button>; })}</div></div>} {history.length > 0 && <p className="mt-4 text-xs text-stone-500">Route: {history.join(' → ')}{scene ? ` → ${scene.sceneId}` : ''}</p>}</section>;
};
