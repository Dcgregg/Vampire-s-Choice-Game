import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { gameStateManager } from '../state/gameState';
import { syncManager } from '../sync/syncManager';
import {
  exchangeSession, getMe, logoutApi, claimSave, getAccountSave, PublicUser, CloudSave,
} from '../sync/cloudClient';

interface ClaimConflict { accountSave: CloudSave; anonymousSave: any; playerId: string; }
interface AuthState {
  user: PublicUser | null;
  loading: boolean;
  conflict: ClaimConflict | null;
  login: () => void;
  logout: () => Promise<void>;
  resolveConflict: (strategy: 'use_account' | 'use_anonymous') => Promise<void>;
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
  const processed = useRef(false);

  const linkProgress = useCallback(async () => {
    const playerId = syncManager.getPlayerId();
    const res = await claimSave(playerId);
    if (res.ok) { syncManager.enterAccountMode(res.save); return; }
    if ('conflict' in res && res.conflict) { setConflict({ accountSave: res.accountSave, anonymousSave: res.anonymousSave, playerId }); return; }
    // Nothing to claim (no anon + no account) -> start a fresh account save from local.
    const acct = await getAccountSave().catch(() => null);
    syncManager.enterAccountMode(acct);
  }, []);

  const resolveConflict = useCallback(async (strategy: 'use_account' | 'use_anonymous') => {
    if (!conflict) return;
    const res = await claimSave(conflict.playerId, strategy);
    if (res.ok) syncManager.enterAccountMode(res.save);
    setConflict(null);
  }, [conflict]);

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
  }, []);

  // Touch gameStateManager so the singleton (and its sync attach) is initialised.
  useEffect(() => { void gameStateManager.getState(); }, []);

  return (
    <AuthContext.Provider value={{ user, loading, conflict, login, logout, resolveConflict }}>
      {children}
    </AuthContext.Provider>
  );
};
