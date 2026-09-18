import React from 'react';
import { AlertTriangle, Check, CloudOff, Loader2, RefreshCw } from 'lucide-react';
import { trustedProgressionQueue } from '../../progression/trustedProgressionQueue';
import { useTrustedProgression } from '../../progression/useTrustedProgression';

export const TrustedProgressionStatus: React.FC = () => {
  const snapshot = useTrustedProgression();
  if (!snapshot.enabled || !snapshot.accountActive) return null;

  const waiting = snapshot.status === 'bootstrapping' || snapshot.status === 'pending';
  const attention = ['offline', 'conflict', 'indeterminate', 'rate_limited', 'blocked'].includes(snapshot.status);
  const retryable = ['offline', 'conflict', 'indeterminate', 'rate_limited'].includes(snapshot.status);
  const Icon = waiting ? Loader2 : attention ? AlertTriangle : Check;
  const label = snapshot.confirmedCoins === null
    ? 'Confirmed balance unavailable'
    : `${snapshot.confirmedCoins} confirmed BloodCoins`;

  return (
    <div
      data-testid="trusted-progression-status"
      role="status"
      aria-live="polite"
      className="border-b border-[#2d1e38]/80 bg-[#120b19] px-3 py-2 text-xs text-stone-300"
    >
      <div className="mx-auto flex max-w-4xl flex-wrap items-center justify-center gap-x-3 gap-y-1">
        <span className="inline-flex items-center gap-1.5 font-semibold text-rose-100">
          <Icon className={`h-3.5 w-3.5 ${waiting ? 'animate-spin text-amber-300' : attention ? 'text-amber-300' : 'text-emerald-400'}`} />
          {label}
        </span>
        <span data-testid="trusted-pending-count" className="text-stone-400">
          {snapshot.pendingCount
            ? `${snapshot.pendingCount} choice${snapshot.pendingCount === 1 ? '' : 's'} pending — no reward assumed`
            : 'No pending choices'}
        </span>
        {snapshot.status === 'offline' && (
          <span className="inline-flex items-center gap-1 text-stone-400">
            <CloudOff className="h-3 w-3" /> Offline
          </span>
        )}
        {snapshot.status === 'conflict' && (
          <span className="text-amber-200">
            This account advanced elsewhere. Reconcile, or pause and sign out to keep this story local.
          </span>
        )}
        {snapshot.status === 'indeterminate' && (
          <span className="text-amber-200">
            The last result is uncertain. Reconcile before making another choice.
          </span>
        )}
        {snapshot.status === 'rate_limited' && (
          <span className="text-amber-200">Too many sync attempts. Wait briefly, then reconcile.</span>
        )}
        {retryable && (
          <button
            type="button"
            data-testid="trusted-progression-retry"
            onClick={() => void trustedProgressionQueue.retry()}
            className="inline-flex items-center gap-1 rounded-full border border-[#c5a059]/50 px-2 py-0.5 font-semibold text-[#e5c158] hover:border-[#c5a059]"
          >
            <RefreshCw className="h-3 w-3" /> Reconcile
          </button>
        )}
        {snapshot.status === 'conflict' && (
          <button
            type="button"
            data-testid="trusted-progression-pause"
            onClick={() => trustedProgressionQueue.pauseForAccountSwitch()}
            className="rounded-full border border-white/20 px-2 py-0.5 font-semibold text-stone-300 hover:border-white/40"
          >
            Pause &amp; switch account
          </button>
        )}
      </div>
    </div>
  );
};
