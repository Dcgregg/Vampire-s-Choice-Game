import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { gameStateManager } from '../state/gameState';
import { syncManager } from '../sync/syncManager';
import {
  exchangeSession, getMe, logoutApi, claimSave, getAccountSave, PublicUser, CloudSave,
} from '../sync/cloudClient';

interface ClaimConflict { accountSave: CloudSave; anonymousSave: any; playerId: string; }
type LinkError = 'link_failed' | 'resolve_failed';
interface AuthState {
  user: PublicUser | null;
  loading: boolean;
  conflict: ClaimConflict | null;
  error: LinkError | null;
  resolving: boolean;
  login: () => void;
  logout: () => Promise<void>;
  resolveConflict: (strategy: 'use_account' | 'use_anonymous') => Promise<void>;
  retryLink: () => Promise<void>;
  dismissError: () => void;
}

const AuthContext = createContext<AuthState | null>(null);
export const useAuth = () => {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth outside AuthProvider');
  return ctx;
};

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<PublicUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [conflict, setConflict] = useState<ClaimConflict | null>(null);
  const [error, setError] = useState<LinkError | null>(null);
  const [resolving, setResolving] = useState(false);
  const processed = useRef(false);

  const linkProgress = useCallback(async () => {
    const playerId = syncManager.getPlayerId();
    let res;
    try {
      res = await claimSave(playerId);
    } catch {
      // Backend unreachable: stay anonymous, keep local progress, surface the error.
      setError('link_failed');
      return;
    }
    if (res.ok) { setError(null); syncManager.enterAccountMode(res.save); return; }
    if ('conflict' in res && res.conflict) {
      setError(null);
      setConflict({ accountSave: res.accountSave, anonymousSave: res.anonymousSave, playerId });
      return;
    }
    // Genuinely nothing to claim (new signed-in user) -> start a fresh account save from local.
    if (res.error === 'nothing_to_claim' || res.error === 'http_404') {
      const acct = await getAccountSave().catch(() => null);
      setError(null);
      syncManager.enterAccountMode(acct);
      return;
    }
    // Any other failure: DO NOT treat as a successful link. Remain anonymous.
    setError('link_failed');
  }, []);

  const resolveConflict = useCallback(async (strategy: 'use_account' | 'use_anonymous') => {
    if (!conflict || resolving) return;
    setResolving(true);
    let res;
    try {
      res = await claimSave(conflict.playerId, strategy);
    } catch {
      // Keep the dialog open so the user can retry; discard nothing.
      setResolving(false);
      setError('resolve_failed');
      return;
    }
    setResolving(false);
    if (res.ok) { setError(null); setConflict(null); syncManager.enterAccountMode(res.save); return; }
    // Resolution failed (e.g. account changed concurrently): keep the dialog open.
    setError('resolve_failed');
  }, [conflict, resolving]);

  const retryLink = useCallback(async () => {
    setError(null);
    await linkProgress();
  }, [linkProgress]);

  const dismissError = useCallback(() => setError(null), []);

  useEffect(() => {
    if (processed.current) return;
    processed.current = true;
    const run = async () => {
      // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
      const hash = window.location.hash || '';
      if (hash.includes('session_id=')) {
        const sid = new URLSearchParams(hash.replace(/^#/, '')).get('session_id');
        history.replaceState(null, '', window.location.pathname + window.location.search);
        if (sid) {
          try {
            const u = await exchangeSession(sid);
            setUser(u);
            await linkProgress();
          } catch { /* fall through to unauthenticated */ }
        }
        setLoading(false);
        return;
      }
      const me = await getMe();
      if (me) { setUser(me); await linkProgress(); }
      setLoading(false);
    };
    void run();
  }, [linkProgress]);

  const login = useCallback(() => {
    // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    const redirectUrl = window.location.origin + '/';
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
  }, []);

  const logout = useCallback(async () => {
    await logoutApi();
    syncManager.exitAccountMode();
    setUser(null);
    setError(null);
    setConflict(null);
  }, []);

  // Touch gameStateManager so the singleton (and its sync attach) is initialised.
  useEffect(() => { void gameStateManager.getState(); }, []);

  return (
    <AuthContext.Provider value={{ user, loading, conflict, error, resolving, login, logout, resolveConflict, retryLink, dismissError }}>
      {children}
    </AuthContext.Provider>
  );
};
