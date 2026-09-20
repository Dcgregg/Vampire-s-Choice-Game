import React from 'react';
import { useAuth } from '../../auth/AuthContext';
import { syncManager, SyncStatus, PushConflict } from '../../sync/syncManager';
import { LogIn, LogOut, Cloud, CloudOff, Loader2, AlertTriangle, Check, X, ShieldCheck } from 'lucide-react';
import { getAdminCatalog } from '../../sync/cloudClient';
import { useGameState } from '../../state/useGameState';

const STATUS_META: Record<SyncStatus, { label: string; Icon: any; cls: string }> = {
  idle: { label: 'Local save', Icon: Cloud, cls: 'text-stone-400' },
  syncing: { label: 'Saving…', Icon: Loader2, cls: 'text-amber-300 animate-spin' },
  synced: { label: 'Saved to cloud', Icon: Check, cls: 'text-emerald-400' },
  offline: { label: 'Offline — saved locally', Icon: CloudOff, cls: 'text-stone-400' },
  conflict: { label: 'Action needed', Icon: AlertTriangle, cls: 'text-amber-300' },
  error: { label: 'Sync error', Icon: AlertTriangle, cls: 'text-rose-400' },
};

const SyncChip: React.FC = () => {
  const [status, setStatus] = React.useState<SyncStatus>(syncManager.status);
  React.useEffect(() => syncManager.subscribe(setStatus), []);
  const m = STATUS_META[status];
  return (
    <div
      data-testid="sync-status-chip"
      role="status"
      aria-live="polite"
      aria-label={m.label}
      className="flex items-center gap-1.5 rounded-full border border-white/10 bg-black/50 px-2.5 py-1 text-[10px] font-medium text-stone-300 backdrop-blur-sm"
    >
      <m.Icon className={`h-3 w-3 ${m.cls}`} />
      <span className="hidden sm:inline">{m.label}</span>
    </div>
  );
};

const chapterLabel = (ps: any): string => {
  const p = ps?.progress;
  if (!p) return 'Progress';
  return `Chapter ${p.currentChapter ?? '?'}`;
};

/** Shown when an unsynced local save loses a revision race on PUSH. Both the
 *  device and cloud versions are preserved until the player explicitly chooses. */
const PushConflictModal: React.FC = () => {
  const [conflict, setConflict] = React.useState<PushConflict | null>(syncManager.getPushConflict());
  const [resolving, setResolving] = React.useState(false);
  const [failed, setFailed] = React.useState(false);
  const [confirmCloud, setConfirmCloud] = React.useState(false);
  React.useEffect(() => syncManager.subscribeConflict(setConflict), []);
  if (!conflict) return null;

  const resolve = async (choice: 'local' | 'cloud') => {
    setResolving(true); setFailed(false);
    const ok = await syncManager.resolvePushConflict(choice);
    setResolving(false);
    if (!ok) { setFailed(true); setConfirmCloud(false); }
    // On success the conflict subscription emits null and this modal unmounts.
  };

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/70 p-4" data-testid="push-conflict-modal">
      <div className="w-full max-w-sm rounded-2xl border border-[#c5a059]/40 bg-[#120a1a] p-5 text-center shadow-2xl">
        <h2 className="font-display text-lg font-bold text-[#f5f0e6]">Your progress differs</h2>
        <p className="mt-2 font-narrative text-sm text-stone-300">
          This device has unsynced progress that differs from your cloud save. Nothing has been lost — choose which to keep.
        </p>
        <div className="mt-3 flex justify-center gap-2 text-[11px]">
          <span data-testid="push-conflict-local-info" className="rounded-full border border-rose-900/60 bg-rose-950/40 px-2.5 py-1 text-rose-200">
            This device · {chapterLabel(conflict.local)}
          </span>
          <span data-testid="push-conflict-cloud-info" className="rounded-full border border-[#332244] bg-[#1a1026] px-2.5 py-1 text-[#e5c158]">
            Cloud · {chapterLabel(conflict.cloud.playerState)}
          </span>
        </div>

        {failed && (
          <p
            data-testid="push-conflict-error-msg"
            role="alert"
            className="mt-3 flex items-center justify-center gap-1.5 rounded-lg border border-rose-800/60 bg-rose-950/50 px-3 py-2 text-xs font-semibold text-rose-200"
          >
            <AlertTriangle className="h-3.5 w-3.5" />
            Couldn't resolve that — both versions are safe. Please try again.
          </p>
        )}

        {!confirmCloud ? (
          <div className="mt-5 space-y-2">
            <button
              data-testid="push-conflict-keep-device-btn"
              disabled={resolving}
              onClick={() => void resolve('local')}
              className="w-full rounded-xl border border-rose-900/60 bg-rose-950/40 px-4 py-2.5 text-sm font-semibold text-rose-200 transition-colors hover:border-rose-600 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {resolving ? 'Working…' : "Keep this device's progress"}
            </button>
            <button
              data-testid="push-conflict-keep-cloud-btn"
              disabled={resolving}
              onClick={() => { setFailed(false); setConfirmCloud(true); }}
              className="w-full rounded-xl border border-[#332244] bg-[#1a1026] px-4 py-2.5 text-sm font-semibold text-[#e5c158] transition-colors hover:border-[#c5a059] disabled:cursor-not-allowed disabled:opacity-50"
            >
              Keep cloud progress
            </button>
          </div>
        ) : (
          <div className="mt-5 space-y-2" data-testid="push-conflict-confirm-cloud">
            <p className="font-narrative text-xs text-rose-200">
              This will discard this device's unsynced progress. Continue?
            </p>
            <button
              data-testid="push-conflict-confirm-cloud-btn"
              disabled={resolving}
              onClick={() => void resolve('cloud')}
              className="w-full rounded-xl border border-[#332244] bg-[#1a1026] px-4 py-2.5 text-sm font-semibold text-[#e5c158] transition-colors hover:border-[#c5a059] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {resolving ? 'Working…' : 'Discard device progress, use cloud'}
            </button>
            <button
              data-testid="push-conflict-cancel-cloud-btn"
              disabled={resolving}
              onClick={() => setConfirmCloud(false)}
              className="w-full rounded-xl border border-white/10 bg-black/40 px-4 py-2.5 text-sm font-semibold text-stone-300 transition-colors hover:border-white/30 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Cancel
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

export const AccountBar: React.FC = () => {
  const { user, loading, login, logout, conflict, resolveConflict, error, resolving, retryLink, dismissError } = useAuth();
  const { setScreen } = useGameState();
  const [isAdmin, setIsAdmin] = React.useState(false);
  React.useEffect(() => { if (!user) { setIsAdmin(false); return; } void getAdminCatalog().then((catalog) => setIsAdmin(Boolean(catalog))).catch(() => setIsAdmin(false)); }, [user]);

  return (
    <>
      <div className="fixed right-2 top-2 z-[60] flex items-center gap-2">
        <SyncChip />
        {error && !conflict && (
          <div
            data-testid="account-error-banner"
            role="alert"
            className="flex items-center gap-1.5 rounded-full border border-rose-800/60 bg-rose-950/70 px-2.5 py-1 text-[10px] font-semibold text-rose-200 backdrop-blur-sm"
          >
            <AlertTriangle className="h-3 w-3" />
            <span className="hidden sm:inline">Couldn't link progress</span>
            <button
              data-testid="account-retry-link-btn"
              onClick={() => void retryLink()}
              className="rounded-full border border-rose-500/60 px-1.5 py-0.5 text-[10px] font-bold text-rose-100 transition-colors hover:bg-rose-800/60"
            >
              Retry
            </button>
            <button
              data-testid="account-dismiss-error-btn"
              onClick={dismissError}
              aria-label="Dismiss"
              className="text-rose-300/80 transition-colors hover:text-rose-100"
            >
              <X className="h-3 w-3" />
            </button>
          </div>
        )}
        {loading ? null : user ? (
          <>
          {isAdmin && <button onClick={() => setScreen('admin')} title="Story admin" className="flex h-7 w-7 items-center justify-center rounded-full border border-[#c5a059]/50 text-[#e5c158]"><ShieldCheck className="h-3.5 w-3.5" /></button>}
          <button
            data-testid="account-logout-btn"
            onClick={() => void logout()}
            title={`Signed in as ${user.email}`}
            className="flex items-center gap-1.5 rounded-full border border-[#c5a059]/50 bg-[#160e20]/80 px-2.5 py-1 text-[11px] font-semibold text-[#e5c158] backdrop-blur-sm transition-colors hover:bg-[#22142e]"
          >
            <LogOut className="h-3 w-3" />
            <span className="hidden sm:inline">Sign out</span>
          </button>
          </>
        ) : (
          <button
            data-testid="account-login-btn"
            onClick={login}
            className="flex items-center gap-1.5 rounded-full border border-[#c5a059]/50 bg-[#160e20]/80 px-2.5 py-1 text-[11px] font-semibold text-[#e5c158] backdrop-blur-sm transition-colors hover:bg-[#22142e]"
          >
            <LogIn className="h-3 w-3" />
            <span>Sign in</span>
          </button>
        )}
      </div>

      {conflict && (
        <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/70 p-4" data-testid="claim-conflict-modal">
          <div className="w-full max-w-sm rounded-2xl border border-[#c5a059]/40 bg-[#120a1a] p-5 text-center shadow-2xl">
            <h2 className="font-display text-lg font-bold text-[#f5f0e6]">Two chronicles found</h2>
            <p className="mt-2 font-narrative text-sm text-stone-300">
              Your account already has saved progress, and this device has its own. Which should continue?
            </p>
            {error === 'resolve_failed' && (
              <p
                data-testid="conflict-error-msg"
                role="alert"
                className="mt-3 flex items-center justify-center gap-1.5 rounded-lg border border-rose-800/60 bg-rose-950/50 px-3 py-2 text-xs font-semibold text-rose-200"
              >
                <AlertTriangle className="h-3.5 w-3.5" />
                We couldn't complete that. Both chronicles are safe — please try again.
              </p>
            )}
            <div className="mt-5 space-y-2">
              <button
                data-testid="conflict-use-cloud-btn"
                disabled={resolving}
                onClick={() => void resolveConflict('use_account')}
                className="w-full rounded-xl border border-[#332244] bg-[#1a1026] px-4 py-2.5 text-sm font-semibold text-[#e5c158] transition-colors hover:border-[#c5a059] disabled:cursor-not-allowed disabled:opacity-50"
              >
                {resolving ? 'Working…' : 'Use my cloud progress'}
              </button>
              <button
                data-testid="conflict-use-local-btn"
                disabled={resolving}
                onClick={() => void resolveConflict('use_anonymous')}
                className="w-full rounded-xl border border-rose-900/60 bg-rose-950/40 px-4 py-2.5 text-sm font-semibold text-rose-200 transition-colors hover:border-rose-600 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {resolving ? 'Working…' : "Keep this device's progress"}
              </button>
            </div>
          </div>
        </div>
      )}

      <PushConflictModal />
    </>
  );
};
