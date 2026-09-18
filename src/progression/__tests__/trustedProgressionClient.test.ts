import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  bootstrapTrustedProgression,
  submitTrustedChoice,
  TrustedProgressionError,
} from '../trustedProgressionClient';
import { ChoiceProgressionEvent } from '../contracts';

const ledger = {
  ownerType: 'account',
  coins: { confirmed: 50 },
  achievements: {},
  checkpoint: {
    bookId: 'book1', contentVersion: 1,
    currentSceneId: 'b1_c1_s1', terminal: false,
  },
  progressionRevision: 0,
};

const event: ChoiceProgressionEvent = {
  kind: 'choice',
  eventId: '550e8400-e29b-41d4-a716-446655440000',
  bookId: 'book1',
  contentVersion: 1,
  baseProgressionRevision: 0,
  fromSceneId: 'b1_c1_s1',
  choiceId: 'c1_call_out',
};

const response = (status: number, body: unknown) => ({
  ok: status >= 200 && status < 300,
  status,
  json: vi.fn().mockResolvedValue(body),
}) as unknown as Response;

beforeEach(() => vi.unstubAllGlobals());

describe('trusted progression HTTP client', () => {
  it('bootstraps with credentials and accepts only the authoritative ledger', async () => {
    const fetchMock = vi.fn().mockResolvedValue(response(200, { ledger }));
    vi.stubGlobal('fetch', fetchMock);
    expect(await bootstrapTrustedProgression()).toEqual(ledger);
    expect(fetchMock.mock.calls[0][0]).toContain('/api/me/progression/bootstrap');
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: 'POST', credentials: 'include' });
  });

  it('submits only the choice event and validates the matching response ID', async () => {
    const fetchMock = vi.fn().mockResolvedValue(response(200, {
      status: 'confirmed', eventId: event.eventId,
      ledger: { ...ledger, coins: { confirmed: 60 }, progressionRevision: 1 },
    }));
    vi.stubGlobal('fetch', fetchMock);
    const result = await submitTrustedChoice(event);
    expect(result.ledger.coins.confirmed).toBe(60);
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual(event);
    expect(fetchMock.mock.calls[0][1].credentials).toBe('include');
  });

  it('rejects malformed or browser-forged authoritative balances', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(200, {
      ledger: { ...ledger, coins: { confirmed: '999999' } },
    })));
    await expect(bootstrapTrustedProgression()).rejects.toMatchObject({
      code: 'invalid_response', retryable: false,
    });
  });

  it('maps stable conflict and indeterminate errors without trusting private text', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(409, {
      detail: { error: 'progression_conflict', action: 'refresh_and_retry' },
    })));
    await expect(submitTrustedChoice(event)).rejects.toMatchObject({
      code: 'progression_conflict', status: 409, retryable: false,
    });

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(503, {
      detail: { error: 'progression_indeterminate', retryable: true },
    })));
    await expect(submitTrustedChoice(event)).rejects.toMatchObject({
      code: 'progression_indeterminate', status: 503, retryable: true,
    });
  });

  it('maps network failures to a retryable offline result', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('private network detail')));
    await expect(bootstrapTrustedProgression()).rejects.toEqual(
      new TrustedProgressionError('offline', 0, true),
    );
  });
});

