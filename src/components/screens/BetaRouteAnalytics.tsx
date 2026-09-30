import React from 'react';
import { BarChart3 } from 'lucide-react';
import { BetaRouteAnalytics as Analytics, getAdminReleaseVersions, getBetaReleaseRouteAnalytics } from '../../sync/cloudClient';

export const BetaRouteAnalytics: React.FC = () => {
  const [items, setItems] = React.useState<Analytics[] | null>(null);

  React.useEffect(() => {
    void getAdminReleaseVersions()
      .then((releases) => Promise.all((releases ?? []).filter((release) => release.status === 'staged' && release.betaEnabled).map((release) => getBetaReleaseRouteAnalytics(release.releaseId))))
      .then(setItems)
      .catch(() => setItems([]));
  }, []);

  if (items === null) return <p className="text-sm text-stone-400">Loading private beta signals…</p>;
  if (!items.length) return <p className="text-sm text-stone-400">No active private beta releases yet.</p>;
  return <section className="space-y-3">
    <p className="text-sm text-stone-400">Aggregate only—no tester identities or player saves.</p>
    {items.map((item) => <article key={item.release.releaseId} className="rounded-lg border border-violet-400/25 bg-black/20 p-3">
      <h3 className="flex items-center gap-2 text-sm font-semibold text-violet-100"><BarChart3 className="h-4 w-4" />{item.release.bookId} · v{item.release.version}</h3>
      <p className="mt-2 text-xs text-stone-300">{item.summary.sessionCount} sessions · {item.summary.completedSessionCount} completed · {item.summary.choiceEventCount} choices</p>
      <div className="mt-2 text-xs text-stone-400">{item.topChoices.length ? item.topChoices.slice(0, 3).map((choice) => <p key={`${choice.sceneId}:${choice.choiceId}`}>{choice.sceneId} → {choice.choiceId}: {choice.count}</p>) : <p>No choices recorded yet.</p>}</div>
    </article>)}
  </section>;
};
