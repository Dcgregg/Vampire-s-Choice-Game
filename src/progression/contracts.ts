/**
 * Phase 6 — Trusted Progression CONTRACTS (foundation only).
 *
 * These types describe the client<->server progression protocol that later
 * sub-phases (6B+) will implement. They are intentionally INERT in 6A: nothing
 * in the running application imports or depends on them yet. They exist so the
 * event/ledger shape is reviewed and pinned before any authority code is built.
 *
 * The client NEVER tells the server how many coins to grant or which
 * achievement to unlock. It submits the CHOICE (or lifecycle) it took; the
 * server derives the effect from the trusted, versioned content table.
 */

/** A story choice the player selected, submitted for server validation. */
export interface ChoiceProgressionEvent {
  kind: 'choice';
  /** Client-generated UUID. Idempotency key for a single request. */
  eventId: string;
  bookId: string;
  /** book.version the client authored this event against. */
  contentVersion: number;
  /** The scene the client believes it is on (checkpoint assertion, anti-replay). */
  fromSceneId: string;
  choiceId: string;
  /** Ledger optimistic-concurrency guard. */
  baseProgressionRevision: number;
}

/** A non-choice lifecycle moment (e.g. character creation) that awards rewards. */
export interface LifecycleProgressionEvent {
  kind: 'lifecycle';
  eventId: string;
  bookId: string;
  contentVersion: number;
  /** Named lifecycle rule, e.g. 'character_created'. */
  lifecycleId: string;
  baseProgressionRevision: number;
}

export type ProgressionEvent = ChoiceProgressionEvent | LifecycleProgressionEvent;

export type EventResultStatus = 'confirmed' | 'duplicate' | 'rejected';

export interface EventResult {
  eventId: string;
  status: EventResultStatus;
  /** Present when status === 'rejected'. */
  reason?: string;
}

/** Achievement provenance in the authoritative ledger. */
export type AchievementSource = 'awarded' | 'imported';

export interface PublicLedgerAchievement {
  unlockedAt: number;
  source: AchievementSource;
}

/** The authoritative economy/achievement projection the client renders. */
export interface PublicLedger {
  ownerType: 'anon' | 'account';
  coins: { confirmed: number };
  achievements: { [achievementId: string]: PublicLedgerAchievement };
  checkpoint: { bookId: string; currentSceneId: string };
  progressionRevision: number;
}
