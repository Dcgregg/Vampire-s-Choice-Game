import React from 'react';
import { Eye, RotateCcw } from 'lucide-react';
import { AdminDraft, AdminScene } from '../../sync/cloudClient';
import { resolveStoryTokens, TestPronouns } from '../../story/tokens';

const firstScene = (scenes: AdminScene[]) => [...scenes].sort((a, b) => a.chapterNumber - b.chapterNumber)[0] ?? null;

export const DraftPlaytest: React.FC<{ draft: AdminDraft }> = ({ draft }) => {
  const scenes = draft.scenes ?? [];
  const byId = React.useMemo(() => new Map(scenes.map((scene) => [scene.sceneId, scene])), [scenes]);
  const [sceneId, setSceneId] = React.useState<string | null>(() => firstScene(scenes)?.sceneId ?? null);
  const [name, setName] = React.useState('Alex');
  const [pronouns, setPronouns] = React.useState<TestPronouns>('they');
  const [species, setSpecies] = React.useState('Human');
  const [stats, setStats] = React.useState<Record<string, number>>({ humanity: 100, bloodCoins: 250 });
  React.useEffect(() => { setSceneId(firstScene(scenes)?.sceneId ?? null); setStats({ humanity: 100, bloodCoins: 250 }); }, [draft.draftId, draft.revision]);
  const scene = sceneId ? byId.get(sceneId) ?? null : null;
  const text = (value: string, speaker?: string) => resolveStoryTokens(value, name, pronouns, species, speaker, draft.storyValues ?? {}, draft.relationshipValues ?? {});
  const choose = (next: string | null | undefined, effects: Array<{ target: string; delta: number }> = []) => { setStats((current) => { const updated = { ...current }; effects.forEach((effect) => { updated[effect.target] = (updated[effect.target] ?? 0) + effect.delta; }); return updated; }); setSceneId(next || null); };
  return <section className="mt-6 rounded-xl border border-[#c5a059]/30 bg-[#150f1f] p-5"><div className="flex justify-between gap-3"><div><h2 className="flex items-center gap-2 font-display text-xl text-[#f5f0e6]"><Eye className="h-5 w-5 text-[#e5c158]" />Draft playtest</h2><p className="text-sm text-stone-400">Private mechanics only. It never changes a real player save.</p></div><button onClick={() => { setSceneId(firstScene(scenes)?.sceneId ?? null); setStats({ humanity: 100, bloodCoins: 250 }); }} className="text-sm text-stone-200"><RotateCcw className="inline h-4 w-4" /> Restart</button></div><div className="mt-3 flex flex-wrap gap-2">{Object.entries(stats).map(([key, value]) => <span key={key} className="rounded border border-[#c5a059]/40 px-2 py-1 text-xs text-[#e5c158]">{key}: {value}</span>)}</div><div className="mt-3 grid gap-2 sm:grid-cols-3"><input value={name} onChange={(e) => setName(e.target.value)} aria-label="Test player name" className="rounded border border-white/15 bg-black/20 p-2" /><select value={pronouns} onChange={(e) => setPronouns(e.target.value as TestPronouns)} className="rounded border border-white/15 bg-black/20 p-2"><option value="they">they/them</option><option value="she">she/her</option><option value="he">he/him</option></select><input value={species} onChange={(e) => setSpecies(e.target.value)} aria-label="Test species" className="rounded border border-white/15 bg-black/20 p-2" /></div>{!scene ? <p className="mt-5 text-stone-400">End of this route.</p> : <article className="mt-5 rounded border border-white/10 bg-black/15 p-5"><h3 className="font-display text-2xl text-[#f5f0e6]">{text(scene.title)}</h3><p className="mt-4 whitespace-pre-wrap text-stone-200">{text(scene.body)}</p>{(scene.dialogue ?? []).map((line, index) => { const speaker = text(line.displayName); return <div key={`${line.speakerId}-${index}`} className="mt-3 flex gap-3 rounded bg-[#25182d] p-3"><div className="flex h-10 w-10 items-center justify-center rounded-full bg-[#7d0828] text-[#f5f0e6]">{speaker.slice(0, 1)}</div><div><strong className="text-[#e5c158]">{speaker}</strong><p className="text-sm text-stone-100">{text(line.text, speaker)}</p></div></div>})}<div className="mt-5 grid gap-2">{scene.choices.map((choice) => <button key={choice.choiceId} onClick={() => choose(choice.nextSceneId, choice.effects ?? [])} className="rounded border border-[#c5a059]/40 p-3 text-left text-[#f5f0e6]">{text(choice.text)}</button>)}</div></article>}</section>;
};
