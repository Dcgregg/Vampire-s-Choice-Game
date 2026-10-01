import React from 'react';
import { FlaskConical, RotateCcw, ShieldCheck } from 'lucide-react';
import { AdminCondition, getNarrativeConversionPreview, NarrativeConversionPreview } from '../../sync/cloudClient';

type CandidateChoice = { id: string; text: string; nextSceneId: string; endsBook?: boolean; consequencesSummary?: string | null };
type CandidateScene = { id: string; chapterNumber: number; chapterTitle: string; sceneTitle: string; paragraphs: string[]; dialogues?: Array<{ speaker: string; text: string }>; choices: CandidateChoice[] };
type CandidateBundle = { book: { title: string; version: number; startingSceneId: string }; scenes: CandidateScene[] };
type ContractChoice = { conditions?: AdminCondition[]; costs?: Array<{ target: string; delta: number }>; effects?: Array<{ target: string; delta: number }> };

const passes = (stats: Record<string, number>, condition: AdminCondition) => condition.operator === 'gte' ? (stats[condition.target] ?? 0) >= condition.value : condition.operator === 'lte' ? (stats[condition.target] ?? 0) <= condition.value : (stats[condition.target] ?? 0) === condition.value;
const label = (condition: AdminCondition) => `${condition.target} ${condition.operator === 'gte' ? '≥' : condition.operator === 'lte' ? '≤' : '='} ${condition.value}`;

export const NarrativeConversionSandbox: React.FC<{ releaseId: string }> = ({ releaseId }) => {
  const [preview, setPreview] = React.useState<NarrativeConversionPreview | null | undefined>(undefined);
  const [sceneId, setSceneId] = React.useState<string | null>(null);
  const [stats, setStats] = React.useState<Record<string, number>>({});
  const [complete, setComplete] = React.useState(false);
  React.useEffect(() => { void getNarrativeConversionPreview(releaseId).then((next) => { setPreview(next); const bundle = next.playerBundleCandidate as CandidateBundle; setSceneId(bundle.book.startingSceneId); setStats({ humanity: next.trustedContract.humanityInitial, bloodCoins: 250 }); }).catch(() => setPreview(null)); }, [releaseId]);
  if (preview === undefined) return <div className="mx-auto max-w-3xl p-8 text-stone-400">Loading converted-content sandbox…</div>;
  if (!preview) return <div className="mx-auto max-w-3xl p-10 text-center text-stone-300"><FlaskConical className="mx-auto h-8 w-8 text-amber-200" /><h1 className="mt-4 font-display text-2xl">Controlled approval required</h1><p className="mt-2 text-sm text-stone-400">This sandbox is available only to an administrator after controlled publication approval.</p></div>;
  const bundle = preview.playerBundleCandidate as CandidateBundle;
  const scene = bundle.scenes.find((item) => item.id === sceneId) ?? null;
  const choose = (choice: CandidateChoice) => {
    if (!scene) return;
    const contract = preview.trustedContract.choices[`${scene.id}:${choice.id}`] as ContractChoice | undefined;
    if (!(contract?.conditions ?? []).every((condition) => passes(stats, condition))) return;
    setStats((current) => {
      const next = { ...current };
      for (const effect of [...(contract?.costs ?? []), ...(contract?.effects ?? [])]) next[effect.target] = (next[effect.target] ?? 0) + effect.delta;
      return next;
    });
    if (choice.endsBook) { setComplete(true); return; }
    setSceneId(choice.nextSceneId);
  };
  const restart = () => { setSceneId(bundle.book.startingSceneId); setStats({ humanity: preview.trustedContract.humanityInitial, bloodCoins: 250 }); setComplete(false); };
  return <div className="mx-auto max-w-4xl p-6 sm:p-10"><header className="rounded-xl border border-amber-300/30 bg-amber-950/15 p-5"><p className="text-xs font-semibold uppercase tracking-wider text-amber-200">Admin-only converted-content sandbox · v{bundle.book.version}</p><h1 className="mt-2 font-display text-3xl text-[#f5f0e6]">{bundle.book.title}</h1><p className="mt-2 text-sm text-stone-300">Uses the conversion preview and trusted contract locally in this tab. It never reads or writes a player save.</p></header><section className="mt-6 rounded-xl border border-[#c5a059]/30 bg-[#150f1f] p-5"><div className="flex flex-wrap justify-between gap-3"><div><h2 className="flex items-center gap-2 font-display text-xl text-[#f5f0e6]"><ShieldCheck className="h-5 w-5 text-amber-200" />Converted narrative route</h2><p className="text-sm text-stone-400">Release checksum {preview.release.manifest.sha256.slice(0, 12)}…</p></div><button onClick={restart} className="text-sm text-stone-200"><RotateCcw className="inline h-4 w-4" /> Restart</button></div><div className="mt-3 flex flex-wrap gap-2">{Object.entries(stats).map(([key, value]) => <span key={key} className="rounded border border-[#c5a059]/40 px-2 py-1 text-xs text-[#e5c158]">{key}: {value}</span>)}</div>{complete || !scene ? <div className="mt-5 rounded border border-emerald-400/30 bg-emerald-950/20 p-5"><h3 className="font-display text-xl text-emerald-100">Converted route complete</h3><p className="mt-2 text-sm text-stone-300">This is an isolated conversion check. It did not change production or player data.</p></div> : <article className="mt-5 rounded border border-white/10 bg-black/15 p-5"><p className="text-xs font-semibold uppercase tracking-wider text-[#c5a059]">{scene.chapterTitle} · Scene {scene.chapterNumber}</p><h3 className="mt-2 font-display text-2xl text-[#f5f0e6]">{scene.sceneTitle}</h3>{scene.paragraphs.map((paragraph, index) => <p key={index} className="mt-4 whitespace-pre-wrap text-stone-200">{paragraph}</p>)}{scene.dialogues?.map((line, index) => <div key={index} className="mt-3 rounded bg-[#25182d] p-3"><strong className="text-[#e5c158]">{line.speaker}</strong><p className="mt-1 text-sm text-stone-100">{line.text}</p></div>)}<div className="mt-5 grid gap-2">{scene.choices.map((choice) => { const contract = preview.trustedContract.choices[`${scene.id}:${choice.id}`] as ContractChoice | undefined; const unmet = (contract?.conditions ?? []).filter((condition) => !passes(stats, condition)); return <button key={choice.id} disabled={unmet.length > 0} onClick={() => choose(choice)} className="rounded border border-[#c5a059]/40 p-3 text-left text-[#f5f0e6] disabled:cursor-not-allowed disabled:opacity-40"><span className="font-semibold">{choice.text}</span>{choice.consequencesSummary && <span className="mt-1 block text-xs text-stone-400">{choice.consequencesSummary}</span>}{unmet.length > 0 && <span className="mt-1 block text-xs text-rose-300">Requires: {unmet.map(label).join(' · ')}</span>}</button>; })}</div></article>}<p className="mt-4 text-xs text-stone-500">Sandbox only. The public catalogue and normal player progression are untouched.</p></section></div>;
};
