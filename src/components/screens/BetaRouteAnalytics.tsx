import React from 'react';
import { BarChart3, RefreshCw } from 'lucide-react';
import { BetaRouteAnalytics as Analytics, getAdminReleaseVersions, getBetaReleaseRouteAnalytics } from '../../sync/cloudClient';

export const BetaRouteAnalytics: React.FC = () => {
  const [items, setItems] = React.useState<Analytics[] | null>(null);
  const [refreshing, setRefreshing] = React.useState(false);

  const load = React.useCallback(async () => {
    setRefreshing(true);
    try {
      const releases = await getAdminReleaseVersions();
      const analytics = await Promise.all((releases ?? []).filter((release) => release.status === 'staged' && release.betaEnabled).map((release) => getBetaReleaseRouteAnalytics(release.releaseId)));
      setItems(analytics);
    } catch {
      setItems([]);
    } finally {
      setRefreshing(false);
    }
  }, []);

  React.useEffect(() => {
    void load();
  }, [load]);

  if (items === null) return <p className="text-sm text-stone-400">Loading private beta signals…</p>;
  if (!items.length) return <><button onClick={() => void load()} disabled={refreshing} className="mb-3 inline-flex items-center gap-1 text-xs text-violet-100 disabled:opacity-50"><RefreshCw className="h-3.5 w-3.5" />Refresh</button><p className="text-sm text-stone-400">No active private beta releases yet.</p></>;
  return <section className="space-y-3">
    <div className="flex items-center justify-between gap-2"><p className="text-sm text-stone-400">Aggregate only—no tester identities or player saves.</p><button onClick={() => void load()} disabled={refreshing} className="inline-flex items-center gap-1 text-xs text-violet-100 disabled:opacity-50"><RefreshCw className="h-3.5 w-3.5" />{refreshing ? 'Refreshing…' : 'Refresh'}</button></div>
    {items.map((item) => <article key={item.release.releaseId} className="rounded-lg border border-violet-400/25 bg-black/20 p-3">
      <h3 className="flex items-center gap-2 text-sm font-semibold text-violet-100"><BarChart3 className="h-4 w-4" />{item.release.bookId} · v{item.release.version}</h3>
      <p className="mt-2 text-xs text-stone-300">{item.summary.sessionCount} sessions · {item.summary.completedSessionCount} completed · {item.summary.choiceEventCount} choices</p>
      <div className="mt-2 text-xs text-stone-400">{item.topChoices.length ? item.topChoices.slice(0, 3).map((choice) => <p key={`${choice.sceneId}:${choice.choiceId}`}><span className="text-stone-300">{choice.sceneTitle}</span> → {choice.choiceText}: {choice.count}</p>) : <p>No choices recorded yet.</p>}{item.currentScenes.length ? <p className="mt-2 text-stone-500">Current stop: {item.currentScenes[0].sceneTitle} ({item.currentScenes[0].count})</p> : null}</div>
    </article>)}
  </section>;
};
