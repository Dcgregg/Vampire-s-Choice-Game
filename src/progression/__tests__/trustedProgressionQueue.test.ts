import { beforeEach, describe, expect, it, vi } from 'vitest';
import { PublicLedger, TrustedChoiceResponse } from '../contracts';
import {
  accountQueueScope,
  TrustedProgressionQueue,
  TrustedProgressionSnapshot,
} from '../trustedProgressionQueue';
import { TrustedProgressionError } from '../trustedProgressionClient';

class MemoryStorage {
  values = new Map<string, string>();
  getItem(key: string) { return this.values.get(key) ?? null; }
  setItem(key: string, value: string) { this.values.set(key, value); }
}

const ledger = (
  revision = 0,
  coins = 50,
  scene = 'b1_c1_s1',
): PublicLedger => ({
  ownerType: 'account',
  coins: { confirmed: coins },
  achievements: {},
  checkpoint: {
    bookId: 'book1', contentVersion: 1,
    currentSceneId: scene, terminal: false,
  },
  progressionRevision: revision,
});

const input = (choiceId = 'c1_call_out', fromSceneId = 'b1_c1_s1') => ({
  bookId: 'book1', contentVersion: 1, fromSceneId, choiceId,
});

const confirmed = (eventId: string, next: PublicLedger): TrustedChoiceResponse => ({
  status: 'confirmed', eventId, ledger: next,
});

const deferred = <T,>() => {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
};

const makeQueue = (storage: MemoryStorage, api: any, ids = ['event-1', 'event-2']) =>
  new TrustedProgressionQueue(true, storage, api, () => ids.shift()!, () => 1234);

beforeEach(() => vi.restoreAllMocks());

describe('trusted progression durable queue', () => {
  it('derives a stable, non-PII queue scope per account', async () => {
    const first = await accountQueueScope(' Player@Example.com ');
    expect(first).toBe(await accountQueueScope('player@example.com'));
    expect(first).not.toContain('player');
    expect(first).not.toBe(await accountQueueScope('other@example.com'));
  });

  it('is inert when disabled and never calls the trusted API', async () => {
    const api = { bootstrap: vi.fn(), submit: vi.fn() };
    const queue = new TrustedProgressionQueue(false, new MemoryStorage(), api as any);
    await queue.enterAccount('account-a');
    expect(queue.recordChoice(input())).toBe(true);
    expect(queue.snapshot()).toMatchObject({
      enabled: false, accountActive: false, status: 'disabled', pendingCount: 0,
    });
    expect(api.bootstrap).not.toHaveBeenCalled();
  });

  it('shows pending separately and never assumes an unconfirmed reward', async () => {
    const submission = deferred<TrustedChoiceResponse>();
    const api = {
      bootstrap: vi.fn().mockResolvedValue(ledger()),
      submit: vi.fn().mockReturnValue(submission.promise),
    };
    const queue = makeQueue(new MemoryStorage(), api);
    await queue.enterAccount('account-a');
    expect(queue.recordChoice(input())).toBe(true);
    expect(queue.snapshot()).toMatchObject({
      confirmedCoins: 50, pendingCount: 1, status: 'pending', canChoose: true,
    });
    submission.resolve(confirmed('event-1', ledger(1, 60, 'b1_c1_s2c')));
    await queue.flush();
    expect(queue.snapshot()).toMatchObject({
      confirmedCoins: 60, progressionRevision: 1,
      pendingCount: 0, status: 'ready',
    });
  });

  it('orders character creation before the first choice without assuming its award', async () => {
    const submission = deferred<TrustedChoiceResponse>();
    const api = {
      bootstrap: vi.fn().mockResolvedValue(ledger()),
      submit: vi.fn().mockReturnValue(submission.promise),
    };
    const queue = makeQueue(new MemoryStorage(), api);
    await queue.enterAccount('account-a');
    expect(queue.recordLifecycle('character_created')).toBe(true);
    expect(queue.recordChoice(input())).toBe(true);
    expect(api.submit.mock.calls[0][0]).toMatchObject({
      kind: 'lifecycle', lifecycleId: 'character_created', baseProgressionRevision: 0,
    });
    expect(queue.snapshot()).toMatchObject({ confirmedAchievements: {}, pendingCount: 2 });
    submission.resolve(confirmed('event-1', ledger(1)));
    await queue.flush();
    expect(api.submit.mock.calls[1][0]).toMatchObject({
      kind: 'choice', baseProgressionRevision: 1,
    });
  });

  it('serialises offline choices with predicted revisions but no predicted coins', async () => {
    const first = deferred<TrustedChoiceResponse>();
    const api = {
      bootstrap: vi.fn().mockResolvedValue(ledger()),
      submit: vi.fn()
        .mockReturnValueOnce(first.promise)
        .mockImplementationOnce((event: any) => Promise.resolve(
          confirmed(event.eventId, ledger(2, 70, 'b1_c1_s3')),
        )),
    };
    const queue = makeQueue(new MemoryStorage(), api);
    await queue.enterAccount('account-a');
    queue.recordChoice(input());
    queue.recordChoice(input('c2_choice', 'b1_c1_s2c'));
    expect(queue.snapshot().confirmedCoins).toBe(50);
    expect(queue.snapshot().pendingCount).toBe(2);
    first.resolve(confirmed('event-1', ledger(1, 60, 'b1_c1_s2c')));
    await queue.flush();
    expect(api.submit.mock.calls.map((call: any[]) => call[0].baseProgressionRevision))
      .toEqual([0, 1]);
    expect(queue.snapshot()).toMatchObject({ confirmedCoins: 70, pendingCount: 0 });
  });

  it('persists a network-failed event and reconciles it after reload', async () => {
    const storage = new MemoryStorage();
    const offlineApi = {
      bootstrap: vi.fn().mockResolvedValue(ledger()),
      submit: vi.fn().mockRejectedValue(new TrustedProgressionError('offline', 0, true)),
    };
    const first = makeQueue(storage, offlineApi, ['same-event']);
    await first.enterAccount('account-a');
    first.recordChoice(input());
    await first.flush();
    expect(first.snapshot()).toMatchObject({ status: 'offline', pendingCount: 1, confirmedCoins: 50 });

    const recoveredApi = {
      bootstrap: vi.fn().mockResolvedValue(ledger()),
      submit: vi.fn().mockImplementation((event: any) =>
        Promise.resolve(confirmed(event.eventId, ledger(1, 60, 'b1_c1_s2c')))),
    };
    const recovered = makeQueue(storage, recoveredApi);
    await recovered.enterAccount('account-a');
    expect(recoveredApi.submit.mock.calls[0][0].eventId).toBe('same-event');
    expect(recovered.snapshot()).toMatchObject({ status: 'ready', pendingCount: 0, confirmedCoins: 60 });
  });

  it('keeps conflicts and indeterminate outcomes pending and blocks new choices', async () => {
    for (const error of [
      new TrustedProgressionError('progression_conflict', 409, false),
      new TrustedProgressionError('progression_indeterminate', 503, true),
    ]) {
      const api = {
        bootstrap: vi.fn().mockResolvedValue(ledger()),
        submit: vi.fn().mockRejectedValue(error),
      };
      const queue = makeQueue(new MemoryStorage(), api, ['event']);
      await queue.enterAccount('account-a');
      queue.recordChoice(input());
      await queue.flush();
      expect(queue.snapshot()).toMatchObject({ pendingCount: 1, canChoose: false });
      expect(queue.recordChoice(input('another'))).toBe(false);
    }
  });

  it('keeps a rate-limited event pending for an explicit later retry', async () => {
    const api = {
      bootstrap: vi.fn().mockResolvedValue(ledger()),
      submit: vi.fn().mockRejectedValue(
        new TrustedProgressionError('progression_rate_limited', 429, true),
      ),
    };
    const queue = makeQueue(new MemoryStorage(), api, ['event']);
    await queue.enterAccount('account-a');
    queue.recordChoice(input());
    await queue.flush();
    expect(queue.snapshot()).toMatchObject({
      status: 'rate_limited', pendingCount: 1, canChoose: false,
    });
  });

  it('pauses a conflicted account without deleting its account-scoped intent', async () => {
    const storage = new MemoryStorage();
    const api = {
      bootstrap: vi.fn().mockResolvedValue(ledger()),
      submit: vi.fn().mockRejectedValue(
        new TrustedProgressionError('progression_conflict', 409, false),
      ),
    };
    const queue = makeQueue(storage, api, ['kept-event']);
    await queue.enterAccount('account-a');
    queue.recordChoice(input());
    await queue.flush();
    queue.pauseForAccountSwitch();
    expect(queue.snapshot()).toMatchObject({ status: 'blocked', pendingCount: 1, canChoose: false });

    const returning = makeQueue(storage, api);
    await returning.enterAccount('account-a');
    expect(api.submit.mock.calls.at(-1)?.[0].eventId).toBe('kept-event');
  });

  it('isolates persisted queues by account scope', async () => {
    const storage = new MemoryStorage();
    const api = {
      bootstrap: vi.fn().mockResolvedValue(ledger()),
      submit: vi.fn().mockRejectedValue(new TrustedProgressionError('offline', 0, true)),
    };
    const queue = makeQueue(storage, api, ['account-a-event']);
    await queue.enterAccount('account-a');
    queue.recordChoice(input());
    await queue.flush();
    expect(queue.snapshot().pendingCount).toBe(1);

    await queue.enterAccount('account-b');
    expect(queue.snapshot().pendingCount).toBe(0);
    expect(api.submit).toHaveBeenCalledTimes(1);
  });

  it('does not apply a response that arrives after logout', async () => {
    const submission = deferred<TrustedChoiceResponse>();
    const api = {
      bootstrap: vi.fn().mockResolvedValue(ledger()),
      submit: vi.fn().mockReturnValue(submission.promise),
    };
    const queue = makeQueue(new MemoryStorage(), api);
    await queue.enterAccount('account-a');
    queue.recordChoice(input());
    queue.leaveAccount();
    submission.resolve(confirmed('event-1', ledger(1, 60)));
    await queue.flush();
    expect(queue.snapshot()).toMatchObject({
      accountActive: false, status: 'signed_out', confirmedCoins: null, pendingCount: 0,
    } as Partial<TrustedProgressionSnapshot>);
  });

  it('blocks an authenticated account when a safe queue scope cannot be created', () => {
    const queue = makeQueue(new MemoryStorage(), { bootstrap: vi.fn(), submit: vi.fn() });
    queue.blockAccountActivation();
    expect(queue.snapshot()).toMatchObject({
      accountActive: true,
      status: 'blocked',
      canChoose: false,
      confirmedCoins: null,
    });
    expect(queue.recordChoice(input())).toBe(false);
  });
});
