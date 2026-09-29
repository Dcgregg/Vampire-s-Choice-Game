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
  migrationRequired: boolean;
  login: () => void;
  logout: () => Promise<void>;
  resolveConflict: (strategy: 'use_account' | 'use_anonymous') => Promise<void>;
  retryLink: () => Promise<void>;
  dismissError: () => void;
  importLocalProgress: () => Promise<void>;
  startFreshAccount: () => Promise<void>;
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
  const [migrationRequired, setMigrationRequired] = useState(false);
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

  const importLocalProgress = useCallback(async () => {
    if (!user || resolving) return;
    const playerId = syncManager.getPlayerId();
    let res;
    setResolving(true);
    try {
      res = await claimSave(playerId);
    } catch {
      setResolving(false);
      setError('link_failed');
      return;
    }
    setResolving(false);
    if (res.ok) {
      setError(null);
      setMigrationRequired(false);
      syncManager.enterAccountMode(res.save);
      await activateTrustedProgression(user);
      return;
    }
    if ('conflict' in res && res.conflict) {
      setError(null);
      setConflict({ accountSave: res.accountSave, anonymousSave: res.anonymousSave, playerId });
      return;
    }
    setError('link_failed');
  }, [activateTrustedProgression, resolving, user]);

  const startFreshAccount = useCallback(async () => {
    if (!user || resolving) return;
    setResolving(true);
    // Switch persistence first, then clear only this browser's local copy.
    // The prior account's cloud save remains untouched and will load on sign-in.
    syncManager.enterAccountMode(null);
    gameStateManager.resetAllData();
    setMigrationRequired(false);
    setError(null);
    await activateTrustedProgression(user);
    setResolving(false);
  }, [activateTrustedProgression, resolving, user]);

  const loadAccount = useCallback(async (account: PublicUser) => {
    try {
      const accountSave = await getAccountSave();
      if (accountSave) {
        syncManager.enterAccountMode(accountSave);
        await activateTrustedProgression(account);
        return;
      }
      // A new account must never silently inherit the active browser's story.
      if (gameStateManager.getState().player) setMigrationRequired(true);
      else {
        syncManager.enterAccountMode(null);
        await activateTrustedProgression(account);
      }
    } catch {
      setError('link_failed');
    }
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
      setMigrationRequired(false);
      syncManager.enterAccountMode(res.save);
      if (user) await activateTrustedProgression(user);
      return;
    }
    // Resolution failed (e.g. account changed concurrently): keep the dialog open.
    setError('resolve_failed');
  }, [activateTrustedProgression, conflict, resolving, user]);

  const retryLink = useCallback(async () => {
    setError(null);
    if (user && migrationRequired) await importLocalProgress();
    else if (user) await loadAccount(user);
  }, [importLocalProgress, loadAccount, migrationRequired, user]);

  const dismissError = useCallback(() => setError(null), []);

  useEffect(() => {
    if (processed.current) return;
    processed.current = true;
    const run = async () => {
      const me = await getMe();
      if (me) { setUser(me); await loadAccount(me); }
      setLoading(false);
    };
    void run();
  }, [loadAccount]);

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
    setMigrationRequired(false);
  }, []);

  // Touch gameStateManager so the singleton (and its sync attach) is initialised.
  useEffect(() => { void gameStateManager.getState(); }, []);

  return (
    <AuthContext.Provider value={{ user, loading, conflict, error, resolving, migrationRequired, login, logout, resolveConflict, retryLink, dismissError, importLocalProgress, startFreshAccount }}>
      {children}
    </AuthContext.Provider>
  );
};
