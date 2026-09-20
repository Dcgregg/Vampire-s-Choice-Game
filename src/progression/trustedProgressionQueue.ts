import {
  ChoiceProgressionEvent,
  LifecycleProgressionEvent,
  ProgressionEvent,
  PublicLedger,
  TrustedChoiceResponse,
} from './contracts';
import {
  bootstrapTrustedProgression,
  submitTrustedEvent,
  TrustedProgressionError,
  TrustedProgressionErrorCode,
} from './trustedProgressionClient';
import { TRUSTED_PROGRESSION_ENABLED } from '../sync/config';

const STORAGE_PREFIX = 'vc_trusted_progression_queue_v1:';

export type TrustedQueueStatus =
  | 'disabled'
  | 'signed_out'
  | 'bootstrapping'
  | 'ready'
  | 'pending'
  | 'offline'
  | 'conflict'
  | 'indeterminate'
  | 'rate_limited'
  | 'blocked';

interface PendingEvent {
  event: ProgressionEvent;
  enqueuedAt: number;
  lastError?: TrustedProgressionErrorCode;
}

interface StoredQueue {
  version: 1;
  pending: PendingEvent[];
}

export interface TrustedProgressionSnapshot {
  enabled: boolean;
  accountActive: boolean;
  status: TrustedQueueStatus;
  confirmedCoins: number | null;
  confirmedAchievements: PublicLedger['achievements'] | null;
  progressionRevision: number | null;
  pendingCount: number;
  canChoose: boolean;
  lastError?: TrustedProgressionErrorCode;
}

interface StorageLike {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

const unavailableStorage: StorageLike = {
  getItem: () => null,
  setItem: () => undefined,
};

const browserStorage: StorageLike =
  typeof localStorage === 'undefined' ? unavailableStorage : localStorage;

interface QueueApi {
  bootstrap(): Promise<PublicLedger>;
  submit(event: ProgressionEvent): Promise<TrustedChoiceResponse>;
}

interface ChoiceInput {
  bookId: string;
  contentVersion: number;
  fromSceneId: string;
  choiceId: string;
}

const defaultApi: QueueApi = {
  bootstrap: bootstrapTrustedProgression,
  submit: submitTrustedEvent,
};

const validEvent = (value: unknown): value is ProgressionEvent => {
  if (!value || typeof value !== 'object') return false;
  const event = value as Record<string, unknown>;
  const common = (event.kind === 'choice' || event.kind === 'lifecycle')
    && typeof event.eventId === 'string'
    && typeof event.bookId === 'string'
    && Number.isInteger(event.contentVersion)
    && Number.isInteger(event.baseProgressionRevision)
    && (event.baseProgressionRevision as number) >= 0
  if (!common) return false;
  return event.kind === 'choice'
    ? typeof event.fromSceneId === 'string' && typeof event.choiceId === 'string'
    : typeof event.lifecycleId === 'string';
};

const randomId = (): string => crypto.randomUUID();

export async function accountQueueScope(email: string): Promise<string> {
  const normalized = email.trim().toLowerCase();
  if (!normalized || !crypto?.subtle) throw new Error('account queue scope unavailable');
  const bytes = new TextEncoder().encode(normalized);
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, '0')).join('');
}

export class TrustedProgressionQueue {
  private activeScope: string | null = null;
  private scopeUsable = true;
  private ledger: PublicLedger | null = null;
  private pending: PendingEvent[] = [];
  private status: TrustedQueueStatus;
  private lastError?: TrustedProgressionErrorCode;
  private listeners = new Set<(snapshot: TrustedProgressionSnapshot) => void>();
  private flushing: Promise<void> | null = null;
  private generation = 0;

  constructor(
    private readonly enabled = TRUSTED_PROGRESSION_ENABLED,
    private readonly storage: StorageLike = browserStorage,
    private readonly api: QueueApi = defaultApi,
    private readonly makeId: () => string = randomId,
    private readonly now: () => number = Date.now,
  ) {
    this.status = enabled ? 'signed_out' : 'disabled';
  }

  snapshot(): TrustedProgressionSnapshot {
    const accountActive = this.activeScope !== null;
    const canChoose = !this.enabled || !accountActive || (
      this.ledger !== null
      && this.scopeUsable
      && this.status !== 'bootstrapping'
      && this.status !== 'conflict'
      && this.status !== 'indeterminate'
      && this.status !== 'rate_limited'
      && this.status !== 'blocked'
    );
    return {
      enabled: this.enabled,
      accountActive,
      status: this.status,
      confirmedCoins: this.ledger?.coins.confirmed ?? null,
      confirmedAchievements: this.ledger ? { ...this.ledger.achievements } : null,
      progressionRevision: this.ledger?.progressionRevision ?? null,
      pendingCount: this.pending.length,
      canChoose,
      lastError: this.lastError,
    };
  }

  subscribe(listener: (snapshot: TrustedProgressionSnapshot) => void): () => void {
    this.listeners.add(listener);
    listener(this.snapshot());
    return () => this.listeners.delete(listener);
  }

  private emit(): void {
    const snapshot = this.snapshot();
    this.listeners.forEach((listener) => listener(snapshot));
  }

  private key(): string | null {
    return this.activeScope && this.scopeUsable
      ? `${STORAGE_PREFIX}${this.activeScope}`
      : null;
  }

  private load(): void {
    this.pending = [];
    const key = this.key();
    if (!key) return;
    try {
      const parsed = JSON.parse(this.storage.getItem(key) || 'null') as StoredQueue | null;
      if (parsed?.version !== 1 || !Array.isArray(parsed.pending)) return;
      this.pending = parsed.pending.filter((item) =>
        !!item && typeof item === 'object' && validEvent(item.event)
          && typeof item.enqueuedAt === 'number',
      );
    } catch {
      this.pending = [];
    }
  }

  private persist(): void {
    const key = this.key();
    if (!key) return;
    const stored: StoredQueue = { version: 1, pending: this.pending };
    try { this.storage.setItem(key, JSON.stringify(stored)); } catch { /* fail closed in memory */ }
  }

  async enterAccount(scope: string): Promise<void> {
    if (!this.enabled) return;
    const generation = ++this.generation;
    this.activeScope = scope;
    this.scopeUsable = true;
    this.ledger = null;
    this.lastError = undefined;
    this.load();
    this.status = 'bootstrapping';
    this.emit();
    await this.reconcile(generation);
  }

  leaveAccount(): void {
    ++this.generation;
    this.activeScope = null;
    this.scopeUsable = true;
    this.ledger = null;
    this.pending = [];
    this.lastError = undefined;
    this.status = this.enabled ? 'signed_out' : 'disabled';
    this.emit();
  }

  /** Keep an authenticated account fail-closed when no safe queue scope exists. */
  blockAccountActivation(): void {
    if (!this.enabled) return;
    ++this.generation;
    this.activeScope = 'unavailable';
    this.scopeUsable = false;
    this.ledger = null;
    this.pending = [];
    this.lastError = 'invalid_response';
    this.status = 'blocked';
    this.emit();
  }

  recordChoice(input: ChoiceInput): boolean {
    if (!this.enabled || !this.activeScope) return true;
    if (!this.ledger || !this.snapshot().canChoose || !Number.isInteger(input.contentVersion)) {
      return false;
    }
    const event: ChoiceProgressionEvent = {
      kind: 'choice',
      eventId: this.makeId(),
      bookId: input.bookId,
      contentVersion: input.contentVersion,
      baseProgressionRevision: this.ledger.progressionRevision + this.pending.length,
      fromSceneId: input.fromSceneId,
      choiceId: input.choiceId,
    };
    this.pending.push({ event, enqueuedAt: this.now() });
    this.persist();
    this.status = 'pending';
    this.lastError = undefined;
    this.emit();
    void this.flush();
    return true;
  }

  recordLifecycle(lifecycleId: string): boolean {
    if (!this.enabled || !this.activeScope) return true;
    if (!this.ledger || !this.snapshot().canChoose || !lifecycleId) return false;
    const event: LifecycleProgressionEvent = {
      kind: 'lifecycle',
      eventId: this.makeId(),
      bookId: this.ledger.checkpoint.bookId,
      contentVersion: this.ledger.checkpoint.contentVersion,
      baseProgressionRevision: this.ledger.progressionRevision + this.pending.length,
      lifecycleId,
    };
    this.pending.push({ event, enqueuedAt: this.now() });
    this.persist();
    this.status = 'pending';
    this.lastError = undefined;
    this.emit();
    void this.flush();
    return true;
  }

  async retry(): Promise<void> {
    if (!this.enabled || !this.activeScope || !this.scopeUsable) return;
    this.lastError = undefined;
    this.status = 'bootstrapping';
    this.emit();
    await this.reconcile(this.generation);
  }

  /**
   * Abandon only the head event after the server has durably rejected it as a
   * checkpoint conflict, then reload the authoritative ledger. Confirmed
   * progression is never changed locally by this recovery action.
   */
  async discardConflictingEvent(): Promise<boolean> {
    if (
      !this.enabled
      || !this.activeScope
      || !this.scopeUsable
      || this.status !== 'conflict'
      || this.pending.length === 0
    ) return false;

    const generation = ++this.generation;
    this.pending.shift();
    this.persist();
    this.lastError = undefined;
    this.status = 'bootstrapping';
    this.emit();
    await this.reconcile(generation);
    return true;
  }

  /** Stop reconciliation without deleting the account-scoped pending intent. */
  pauseForAccountSwitch(): void {
    if (!this.enabled || !this.activeScope) return;
    ++this.generation;
    this.status = 'blocked';
    this.emit();
  }

  private async reconcile(generation = this.generation): Promise<void> {
    try {
      const ledger = await this.api.bootstrap();
      if (generation !== this.generation || !this.activeScope) return;
      this.ledger = ledger;
      this.status = this.pending.length ? 'pending' : 'ready';
      this.lastError = undefined;
      this.emit();
      await this.flush();
      // An account switch can leave the previous account's request in flight.
      // Once it drains, start this account's queue rather than sharing work.
      if (generation === this.generation && this.pending.length && !this.flushing) {
        await this.flush();
      }
    } catch (error) {
      if (generation !== this.generation) return;
      this.handleError(error);
    }
  }

  async flush(): Promise<void> {
    if (this.flushing) return this.flushing;
    const generation = this.generation;
    this.flushing = this.flushPending(generation).finally(() => {
      this.flushing = null;
    });
    return this.flushing;
  }

  private async flushPending(generation: number): Promise<void> {
    while (this.activeScope && this.ledger && this.pending.length) {
      const item = this.pending[0];
      try {
        const response = await this.api.submit(item.event);
        if (generation !== this.generation) return;
        this.ledger = response.ledger;
        this.pending.shift();
        this.persist();
        this.status = this.pending.length ? 'pending' : 'ready';
        this.lastError = undefined;
        this.emit();
      } catch (error) {
        if (generation !== this.generation) return;
        this.handleError(error, item);
        return;
      }
    }
  }

  private handleError(error: unknown, item?: PendingEvent): void {
    const trusted = error instanceof TrustedProgressionError
      ? error
      : new TrustedProgressionError('offline', 0, true);
    this.lastError = trusted.code;
    if (item) item.lastError = trusted.code;
    this.persist();
    if (trusted.code === 'offline') this.status = 'offline';
    else if (trusted.code === 'progression_conflict') this.status = 'conflict';
    else if (trusted.code === 'progression_indeterminate') this.status = 'indeterminate';
    else if (trusted.code === 'progression_rate_limited') this.status = 'rate_limited';
    else this.status = 'blocked';
    this.emit();
  }
}

export const trustedProgressionQueue = new TrustedProgressionQueue();
