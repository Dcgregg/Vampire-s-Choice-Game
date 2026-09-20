import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { gameStateManager } from '../state/gameState';
import { syncManager } from '../sync/syncManager';
import {
  getMe, logoutApi, claimSave, getAccountSave, PublicUser, CloudSave,
} from '../sync/cloudClient';
import { TRUSTED_PROGRESSION_ENABLED } from '../sync/config';
import {
  accountQueueScope,
  trustedProgressionQueue,
} from '../progression/trustedProgressionQueue';

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

  const activateTrustedProgression = useCallback(async (account: PublicUser) => {
    if (!TRUSTED_PROGRESSION_ENABLED) return;
    try {
      const scope = await accountQueueScope(account.email);
      await trustedProgressionQueue.enterAccount(scope);
    } catch {
      trustedProgressionQueue.blockAccountActivation();
    }
  }, []);

  const linkProgress = useCallback(async (account: PublicUser) => {
    const playerId = syncManager.getPlayerId();
    let res;
    try {
      res = await claimSave(playerId);
    } catch {
      // Backend unreachable: stay anonymous, keep local progress, surface the error.
      setError('link_failed');
      return;
    }
    if (res.ok) {
      setError(null);
      syncManager.enterAccountMode(res.save);
      await activateTrustedProgression(account);
      return;
    }
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
      await activateTrustedProgression(account);
      return;
    }
    // Any other failure: DO NOT treat as a successful link. Remain anonymous.
    setError('link_failed');
  }, [activateTrustedProgression]);

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
    if (res.ok) {
      setError(null);
      setConflict(null);
      syncManager.enterAccountMode(res.save);
      if (user) await activateTrustedProgression(user);
      return;
    }
    // Resolution failed (e.g. account changed concurrently): keep the dialog open.
    setError('resolve_failed');
  }, [activateTrustedProgression, conflict, resolving, user]);

  const retryLink = useCallback(async () => {
    setError(null);
    if (user) await linkProgress(user);
  }, [linkProgress, user]);

  const dismissError = useCallback(() => setError(null), []);

  useEffect(() => {
    if (processed.current) return;
    processed.current = true;
    const run = async () => {
      const me = await getMe();
      if (me) { setUser(me); await linkProgress(me); }
      setLoading(false);
    };
    void run();
  }, [linkProgress]);

  const login = useCallback(() => {
    window.location.href = '/api/auth/google/start';
  }, []);

  const logout = useCallback(async () => {
    await logoutApi();
    trustedProgressionQueue.leaveAccount();
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
