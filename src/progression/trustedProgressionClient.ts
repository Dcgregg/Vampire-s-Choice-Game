import { API_BASE } from '../sync/config';
import {
  ChoiceProgressionEvent,
  LifecycleProgressionEvent,
  ProgressionEvent,
  PublicLedger,
  TrustedChoiceResponse,
} from './contracts';

export type TrustedProgressionErrorCode =
  | 'offline'
  | 'not_authenticated'
  | 'progression_unavailable'
  | 'invalid_choice'
  | 'invalid_lifecycle'
  | 'progression_conflict'
  | 'progression_indeterminate'
  | 'progression_rate_limited'
  | 'progression_bootstrap_unavailable'
  | 'invalid_response'
  | 'unknown';

export class TrustedProgressionError extends Error {
  constructor(
    public readonly code: TrustedProgressionErrorCode,
    public readonly status: number,
    public readonly retryable: boolean,
  ) {
    super(code);
    this.name = 'TrustedProgressionError';
  }
}

const isObject = (value: unknown): value is Record<string, unknown> =>
  !!value && typeof value === 'object' && !Array.isArray(value);

function parseLedger(value: unknown): PublicLedger {
  if (!isObject(value) || value.ownerType !== 'account') {
    throw new TrustedProgressionError('invalid_response', 0, false);
  }
  const coins = value.coins;
  const checkpoint = value.checkpoint;
  const revision = value.progressionRevision;
  if (
    !isObject(coins) ||
    !Number.isInteger(coins.confirmed) ||
    (coins.confirmed as number) < 0 ||
    !isObject(value.achievements) ||
    !isObject(checkpoint) ||
    typeof checkpoint.bookId !== 'string' ||
    !Number.isInteger(checkpoint.contentVersion) ||
    typeof checkpoint.currentSceneId !== 'string' ||
    typeof checkpoint.terminal !== 'boolean' ||
    !Number.isInteger(revision) ||
    (revision as number) < 0
  ) {
    throw new TrustedProgressionError('invalid_response', 0, false);
  }
  return {
    ownerType: 'account',
    coins: { confirmed: coins.confirmed as number },
    achievements: value.achievements as PublicLedger['achievements'],
    checkpoint: {
      bookId: checkpoint.bookId,
      contentVersion: checkpoint.contentVersion as number,
      currentSceneId: checkpoint.currentSceneId,
      terminal: checkpoint.terminal,
    },
    progressionRevision: revision as number,
  };
}

async function request(path: string, init: RequestInit): Promise<unknown> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'X-VC-Progression': '1',
        ...(init.headers || {}),
      },
    });
  } catch {
    throw new TrustedProgressionError('offline', 0, true);
  }
  const body = await response.json().catch(() => ({}));
  if (response.ok) return body;
  const detail = isObject(body) && isObject(body.detail) ? body.detail : body;
  const rawCode = isObject(detail) && typeof detail.error === 'string'
    ? detail.error
    : response.status === 401
    ? 'not_authenticated'
    : 'unknown';
  const retryable = isObject(detail) && typeof detail.retryable === 'boolean'
    ? detail.retryable
    : response.status >= 500;
  throw new TrustedProgressionError(
    rawCode as TrustedProgressionErrorCode,
    response.status,
    retryable,
  );
}

export async function bootstrapTrustedProgression(): Promise<PublicLedger> {
  const body = await request('/me/progression/bootstrap', { method: 'POST' });
  if (!isObject(body)) throw new TrustedProgressionError('invalid_response', 0, false);
  return parseLedger(body.ledger);
}

export async function submitTrustedChoice(
  event: ChoiceProgressionEvent,
): Promise<TrustedChoiceResponse> {
  const body = await request('/me/progression/choices', {
    method: 'POST',
    body: JSON.stringify(event),
  });
  if (
    !isObject(body) ||
    body.eventId !== event.eventId ||
    (body.status !== 'confirmed' && body.status !== 'duplicate')
  ) {
    throw new TrustedProgressionError('invalid_response', 0, false);
  }
  return {
    eventId: body.eventId,
    status: body.status,
    ledger: parseLedger(body.ledger),
  };
}

export async function submitTrustedLifecycle(
  event: LifecycleProgressionEvent,
): Promise<TrustedChoiceResponse> {
  const body = await request('/me/progression/lifecycle', {
    method: 'POST',
    body: JSON.stringify(event),
  });
  if (
    !isObject(body) ||
    body.eventId !== event.eventId ||
    (body.status !== 'confirmed' && body.status !== 'duplicate')
  ) {
    throw new TrustedProgressionError('invalid_response', 0, false);
  }
  return {
    eventId: body.eventId,
    status: body.status,
    ledger: parseLedger(body.ledger),
  };
}

export function submitTrustedEvent(event: ProgressionEvent): Promise<TrustedChoiceResponse> {
  return event.kind === 'choice'
    ? submitTrustedChoice(event)
    : submitTrustedLifecycle(event);
}
