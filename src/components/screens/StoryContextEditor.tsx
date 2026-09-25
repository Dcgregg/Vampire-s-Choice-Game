import React from 'react';
import { Plus, Trash2 } from 'lucide-react';

type Values = Record<string, string>;

function valueRows(values: Values) { return Object.entries(values).length ? Object.entries(values) : [['', '']]; }

const ValueGroup: React.FC<{ title: string; tokenPrefix: string; values: Values; onChange: (values: Values) => void }> = ({ title, tokenPrefix, values, onChange }) => {
  const rows = valueRows(values);
  const replace = (index: number, key: string, value: string) => {
    const next: Values = {};
    rows.forEach(([oldKey, oldValue], rowIndex) => { const nextKey = rowIndex === index ? key : oldKey; const nextValue = rowIndex === index ? value : oldValue; if (nextKey.trim()) next[nextKey.trim()] = nextValue; });
    onChange(next);
  };
  const remove = (index: number) => { const next: Values = {}; rows.filter((_, rowIndex) => rowIndex !== index).forEach(([key, value]) => { if (key) next[key] = value; }); onChange(next); };
  return <div className="mt-4"><p className="text-sm font-semibold text-[#c5a059]">{title}</p><p className="mt-1 text-xs text-stone-400">Use <code>{`{{${tokenPrefix}.key}}`}</code> in prose, dialogue, or choice text.</p>{rows.map(([key, value], index) => <div className="mt-2 flex gap-2" key={`${key}-${index}`}><input value={key} onChange={(event) => replace(index, event.target.value, value)} placeholder="key, e.g. humanity" className="min-w-0 flex-1 rounded border border-white/15 bg-black/20 p-2 text-sm text-[#f5f0e6]" /><input value={value} onChange={(event) => replace(index, key, event.target.value)} placeholder="Current test value" className="min-w-0 flex-1 rounded border border-white/15 bg-black/20 p-2 text-sm text-[#f5f0e6]" /><button onClick={() => remove(index)} className="text-rose-300" title="Remove value"><Trash2 className="h-4 w-4" /></button></div>)}<button onClick={() => onChange({ ...values, [`value${rows.length + 1}`]: '' })} className="mt-2 inline-flex items-center gap-1 text-sm text-[#e5c158]"><Plus className="h-4 w-4" />Add value</button></div>;
};

export const StoryContextEditor: React.FC<{ storyValues: Values; relationshipValues: Values; onChange: (storyValues: Values, relationshipValues: Values) => void }> = ({ storyValues, relationshipValues, onChange }) => <details className="mt-4 rounded border border-white/10 bg-black/15 p-3"><summary className="cursor-pointer text-sm font-semibold text-[#e5c158]">Story values & relationships</summary><ValueGroup title="Story values" tokenPrefix="story" values={storyValues} onChange={(next) => onChange(next, relationshipValues)} /><ValueGroup title="Relationship values" tokenPrefix="relationship" values={relationshipValues} onChange={(next) => onChange(storyValues, next)} /></details>;
