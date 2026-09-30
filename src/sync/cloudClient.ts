/**
 * Thin HTTP client for the cloud save API. All calls fail loudly (throw) on
 * network/unknown errors so the sync manager can treat the backend as
 * unavailable and keep the game running on local storage.
 */
import { API_BASE } from './config';

export interface CloudSave {
  playerId: string;
  saveSchemaVersion: number;
  contentVersions: { [bookId: string]: number };
  playerState: any;
  revision: number;
  createdAt: string;
  updatedAt: string;
}

export interface SavePayload {
  saveSchemaVersion: number;
  contentVersions: { [bookId: string]: number };
  playerState: any;
  baseRevision: number;
}

export async function health(): Promise<boolean> {
  try {
    const r = await fetch(`${API_BASE}/health`);
    return r.ok;
  } catch {
    return false;
  }
}

export async function getSave(playerId: string): Promise<CloudSave | null> {
  const r = await fetch(`${API_BASE}/saves/${playerId}`);
  if (r.status === 404) return null;
  if (!r.ok) throw new Error(`getSave failed: ${r.status}`);
  return (await r.json()) as CloudSave;
}

export interface PutResult {
  ok: boolean;
  save?: CloudSave;
  currentSave?: CloudSave | null;
}

export async function putSave(playerId: string, payload: SavePayload): Promise<PutResult> {
  const r = await fetch(`${API_BASE}/saves/${playerId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (r.status === 409) {
    const body = await r.json().catch(() => ({}));
    return { ok: false, currentSave: body.currentSave ?? null };
  }
  if (!r.ok) throw new Error(`putSave failed: ${r.status}`);
  return { ok: true, save: (await r.json()) as CloudSave };
}

// ---- Authenticated (account) endpoints — rely on the httpOnly session cookie ----
export interface PublicUser { email: string; name: string; picture?: string | null; }
export interface AdminCatalog {
  series: Array<{ id: string; order: number; status: string }>;
  books: Array<{ id: string; version: number; startingSceneId: string; sceneCount: number }>;
}

export interface AdminDraft {
  draftId: string;
  bookId: string;
  title: string;
  synopsis: string;
  branchNotes: string;
  storyValues: Record<string, string>;
  relationshipValues: Record<string, string>;
  playtestValues: Record<string, number>;
  scenes: AdminScene[];
  status: 'draft' | 'ready_for_review' | 'approved_for_release' | 'archived';
  reviewApproval?: { approvedAt: string; approvedBy: string; approvedRevision: number } | null;
  reviewHistory?: AdminReviewApproval[];
  revision: number;
  createdAt: string;
  updatedAt: string;
  updatedBy: string;
}

export interface AdminReviewApproval { approvedAt: string; approvedBy: string; approvedRevision: number; }
export interface AdminReleaseVersion {
  releaseId: string;
  bookId: string;
  version: number;
  status: 'prepared' | 'selected' | 'staged';
  source: { draftId: string; approvedRevision: number; currentRevision: number };
  manifest: { sha256: string; sceneCount: number; playerFacing: false; published: false };
  createdAt: string;
  createdBy: string;
  selectedAt?: string | null;
  selectedBy?: string | null;
  stagedAt?: string | null;
  stagedBy?: string | null;
  betaEnabled?: boolean;
  betaEnabledAt?: string | null;
  betaEnabledBy?: string | null;
  betaDecision?: BetaDecision | null;
  betaDecisionHistory?: BetaDecision[];
  publicationApproval?: PublicationApproval | null;
  publicationApprovalHistory?: PublicationApproval[];
  catalogueRegistration?: CatalogueRegistration | null;
}
export type AdminReleaseSnapshot = AdminReleaseVersion & { snapshot: AdminDraft; playerFacing: false; published: false };
export interface StagedReleasePreview { format: string; environment: 'staging-preview'; playerFacing: true; published: false; release: AdminReleaseVersion; snapshot: AdminDraft; note: string; }
export interface StagedPreviewAudit { kind: 'cost' | 'effect'; target: string; before: number; delta: number; after: number; }
export interface StagedPreviewSession { sessionId: string; sessionToken?: string; bookId: string; releaseId: string; contentVersion: number; sceneId: string | null; stats: Record<string, number>; history: Array<{ sceneId: string; choiceId: string; audit: StagedPreviewAudit[]; at: string }>; revision: number; createdAt: string; updatedAt: string; expiresAt: string; stagingOnly: true; }
export interface BetaReleasePreview { format: string; environment: 'beta'; release: AdminReleaseVersion; snapshot: AdminDraft; note: string; }
export interface BetaPlayerSession { sessionId: string; bookId: string; releaseId: string; contentVersion: number; sceneId: string | null; stats: Record<string, number>; history: Array<{ sceneId: string; choiceId: string; audit: StagedPreviewAudit[]; at: string }>; revision: number; createdAt: string; updatedAt: string; betaOnly: true; }
export interface BetaDecision { decision: 'continue_testing' | 'ready_for_release_review'; note: string; decidedAt: string; decidedBy: string; openFeedbackCount: number; playerFacing: false; published: false; }
export interface PublicationApproval { checksum: string; version: number; note: string; approvedAt: string; approvedBy: string; playerFacing: false; published: false; }
export interface CatalogueRegistration { candidateId: string; releaseId: string; bookId: string; releaseVersion: number; checksum: string; status: 'registered' | 'invalidated' | 'withdrawn'; registeredAt: string; registeredBy: string; registrationRevision: number; playerFacing: false; published: false; note: string; }
export interface CatalogueActivationPreflight { format: 'vampires-choice-catalogue-activation-preflight/v1'; checkedAt: string; candidate: CatalogueRegistration; checks: Array<{ id: string; passed: boolean; message: string }>; activationReady: false; productionPublished: false; rollbackPlan: { action: string; playerSavesTouched: 0; playerCatalogueChanged: false }; note: string; }
export interface BetaReadiness { releaseId: string; bookId: string; version: number; enabled: boolean; featureEnabled: boolean; invitedCount: number; sessionCount: number; completedSessionCount: number; feedbackCount: number; openFeedbackCount: number; resolvedFeedbackCount: number; readyForDecision: boolean; decision?: BetaDecision | null; accountSavesTouched: 0; productionPublished: false; }
export interface BetaFeedback { feedbackId: string; sessionId: string; testerEmail: string; message: string; createdAt: string; status: 'open' | 'resolved'; adminNote: string; resolvedAt?: string | null; resolvedBy?: string | null; }
export interface BetaReport { format: 'vampires-choice-private-beta-report/v1'; exportedAt: string; release: AdminReleaseVersion; summary: { enabled: boolean; invitedCount: number; sessionCount: number; completedSessionCount: number; feedbackCount: number; openFeedbackCount: number; resolvedFeedbackCount: number; readyForReleaseReview: boolean; decision?: BetaDecision | null; }; feedback: Array<Omit<BetaFeedback, 'sessionId' | 'resolvedBy'>>; publication: { playerFacing: false; published: false; note: string; }; }
export interface BetaRouteAnalytics { format: 'vampires-choice-private-beta-route-analytics/v1'; generatedAt: string; release: Pick<AdminReleaseVersion, 'releaseId' | 'bookId' | 'version'>; summary: { sessionCount: number; completedSessionCount: number; activeSessionCount: number; choiceEventCount: number }; topChoices: Array<{ sceneId: string; choiceId: string; count: number }>; currentScenes: Array<{ sceneId: string; count: number }>; privacy: { testerIdentitiesIncluded: false; playerSavesTouched: 0; published: false }; note: string; }
export interface PublicationHandoff { format: 'vampires-choice-controlled-publication-handoff/v1'; exportedAt: string; release: AdminReleaseVersion; snapshot: AdminDraft; compatibility: { sourceFormat: string; targetFormat: string; requiresTrustedContentConversion: true; checksum: string; note: string; }; publication: { playerFacing: false; published: false; note: string; }; }
export interface TrustedContentCompatibility { format: 'vampires-choice-trusted-content-compatibility/v1'; checkedAt: string; releaseId: string; checksum: string; summary: { blockingIssueCount: number; requiredWorkCount: number; supportedEffectCount: number; unsupportedEffectCount: number; eligibleForTrustedConversion: boolean; }; supportedMappings: Record<string, string>; issues: Array<{ severity: 'blocking' | 'required'; code: string; message: string; sceneId?: string; choiceId?: string; target?: string; }>; publication: { playerFacing: false; published: false; note: string; }; }
export interface NarrativeConversionPreview { format: 'vampires-choice-narrative-conversion-preview/v1'; exportedAt: string; release: AdminReleaseVersion; playerBundleCandidate: unknown; trustedContract: { humanityInitial: number; humanityMin: number; humanityMax: number; choices: Record<string, unknown>; }; warnings: string[]; publication: { playerFacing: false; published: false; note: string; }; }

export interface AdminChoice {
  choiceId: string;
  text: string;
  nextSceneId?: string | null;
  effectsNotes: string;
  conditions?: AdminCondition[];
  costs?: AdminEffect[];
  effects?: AdminEffect[];
}
export interface AdminEffect { target: string; delta: number; }
export interface AdminCondition { target: string; operator: 'gte' | 'lte' | 'eq'; value: number; }

export interface AdminDialogue {
  speakerId: string;
  displayName: string;
  text: string;
  mood: string;
}
export interface AdminCharacter { characterId: string; displayName: string; defaultMood: string; }

export interface AdminScene {
  sceneId: string;
  chapterNumber: number;
  title: string;
  body: string;
  dialogue?: AdminDialogue[];
  choices: AdminChoice[];
}

export type AdminDraftInput = Pick<AdminDraft, 'bookId' | 'title' | 'synopsis' | 'branchNotes' | 'storyValues' | 'relationshipValues' | 'playtestValues'>;
export interface AdminDraftValidation { draftId: string; valid: boolean; issues: Array<{ code: string; message: string }>; }
export interface AdminDraftReviewExport { format: string; draft: AdminDraft; [key: string]: unknown; }
export interface AdminAiStatus { configured: boolean; model: string | null; }
export interface AdminAiDraftRequest { bookId: string; premise: string; desiredTitle: string; }

export async function getMe(): Promise<PublicUser | null> {
  const r = await fetch(`${API_BASE}/auth/me`, { credentials: 'include' });
  if (!r.ok) return null;
  return (await r.json()) as PublicUser;
}

export async function getAdminCatalog(): Promise<AdminCatalog | null> {
  const r = await fetch(`${API_BASE}/admin/content-catalog`, { credentials: 'include' });
  if (r.status === 401 || r.status === 403) return null;
  if (!r.ok) throw new Error(`getAdminCatalog failed: ${r.status}`);
  return (await r.json()) as AdminCatalog;
}

export async function getAdminCharacters(): Promise<AdminCharacter[] | null> {
  const r = await fetch(`${API_BASE}/admin/characters`, { credentials: 'include' });
  if (r.status === 401 || r.status === 403) return null;
  if (!r.ok) throw new Error(`getAdminCharacters failed: ${r.status}`);
  return ((await r.json()) as { characters: AdminCharacter[] }).characters;
}

export async function createAdminCharacter(input: AdminCharacter): Promise<AdminCharacter> {
  const r = await fetch(`${API_BASE}/admin/characters`, { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input) });
  if (!r.ok) throw new Error(`createAdminCharacter failed: ${r.status}`);
  return (await r.json()) as AdminCharacter;
}

export async function updateAdminCharacter(input: AdminCharacter): Promise<AdminCharacter> {
  const r = await fetch(`${API_BASE}/admin/characters/${input.characterId}`, { method: 'PUT', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input) });
  if (!r.ok) throw new Error(`updateAdminCharacter failed: ${r.status}`);
  return (await r.json()) as AdminCharacter;
}

export async function deleteAdminCharacter(characterId: string): Promise<void> {
  const r = await fetch(`${API_BASE}/admin/characters/${characterId}`, { method: 'DELETE', credentials: 'include' });
  if (!r.ok) throw new Error(`deleteAdminCharacter failed: ${r.status}`);
}

export async function getAdminDrafts(): Promise<AdminDraft[] | null> {
  const r = await fetch(`${API_BASE}/admin/drafts`, { credentials: 'include' });
  if (r.status === 401 || r.status === 403) return null;
  if (!r.ok) throw new Error(`getAdminDrafts failed: ${r.status}`);
  return ((await r.json()) as { drafts: AdminDraft[] }).drafts;
}

export async function getAdminAiStatus(): Promise<AdminAiStatus | null> {
  const r = await fetch(`${API_BASE}/admin/ai/status`, { credentials: 'include' });
  if (r.status === 401 || r.status === 403) return null;
  if (!r.ok) throw new Error(`getAdminAiStatus failed: ${r.status}`);
  return (await r.json()) as AdminAiStatus;
}

export async function createAdminDraft(input: AdminDraftInput): Promise<AdminDraft> {
  const r = await fetch(`${API_BASE}/admin/drafts`, {
    method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input),
  });
  if (!r.ok) throw new Error(`createAdminDraft failed: ${r.status}`);
  return (await r.json()) as AdminDraft;
}

export async function createSampleAdminDraft(): Promise<AdminDraft> {
  const r = await fetch(`${API_BASE}/admin/drafts/sample`, { method: 'POST', credentials: 'include' });
  if (!r.ok) throw new Error(`createSampleAdminDraft failed: ${r.status}`);
  return (await r.json()) as AdminDraft;
}
export async function createBookTwoStarterDraft(): Promise<AdminDraft> {
  const r = await fetch(`${API_BASE}/admin/drafts/book-two-starter`, { method: 'POST', credentials: 'include' });
  if (!r.ok) throw new Error(`createBookTwoStarterDraft failed: ${r.status}`);
  return (await r.json()) as AdminDraft;
}

export async function importAdminBookJson(content: Record<string, unknown>): Promise<AdminDraft> {
  const r = await fetch(`${API_BASE}/admin/drafts/import-book-json`, { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ content }) });
  if (!r.ok) throw new Error(`importAdminBookJson failed: ${r.status}`);
  return (await r.json()) as AdminDraft;
}

export async function generateAdminDraft(input: AdminAiDraftRequest): Promise<AdminDraft> {
  const r = await fetch(`${API_BASE}/admin/drafts/generate`, { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input) });
  if (r.status === 503) throw new Error('openrouter_not_configured');
  if (!r.ok) throw new Error(`generateAdminDraft failed: ${r.status}`);
  return (await r.json()) as AdminDraft;
}

export async function updateAdminDraft(draftId: string, input: AdminDraftInput, baseRevision: number): Promise<AdminDraft> {
  const r = await fetch(`${API_BASE}/admin/drafts/${draftId}`, {
    method: 'PUT', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...input, baseRevision }),
  });
  if (r.status === 409) throw new Error('draft_conflict');
  if (!r.ok) throw new Error(`updateAdminDraft failed: ${r.status}`);
  return (await r.json()) as AdminDraft;
}

export async function updateAdminDraftScenes(draftId: string, scenes: AdminScene[], baseRevision: number): Promise<AdminDraft> {
  const r = await fetch(`${API_BASE}/admin/drafts/${draftId}/scenes`, {
    method: 'PUT', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ scenes, baseRevision }),
  });
  if (r.status === 409) throw new Error('draft_conflict');
  if (!r.ok) throw new Error(`updateAdminDraftScenes failed: ${r.status}`);
  return (await r.json()) as AdminDraft;
}

export async function requestAdminDraftReview(draftId: string): Promise<AdminDraft> {
  const r = await fetch(`${API_BASE}/admin/drafts/${draftId}/request-review`, { method: 'POST', credentials: 'include' });
  if (!r.ok) throw new Error(`requestAdminDraftReview failed: ${r.status}`);
  return (await r.json()) as AdminDraft;
}

export async function approveAdminDraftRelease(draftId: string): Promise<AdminDraft> {
  const r = await fetch(`${API_BASE}/admin/drafts/${draftId}/approve-release`, { method: 'POST', credentials: 'include' });
  if (!r.ok) throw new Error(`approveAdminDraftRelease failed: ${r.status}`);
  return (await r.json()) as AdminDraft;
}

export async function archiveAdminDraft(draftId: string): Promise<AdminDraft> {
  const r = await fetch(`${API_BASE}/admin/drafts/${draftId}/archive`, { method: 'POST', credentials: 'include' });
  if (!r.ok) throw new Error(`archiveAdminDraft failed: ${r.status}`);
  return (await r.json()) as AdminDraft;
}

export async function restoreAdminDraft(draftId: string): Promise<AdminDraft> {
  const r = await fetch(`${API_BASE}/admin/drafts/${draftId}/restore`, { method: 'POST', credentials: 'include' });
  if (!r.ok) throw new Error(`restoreAdminDraft failed: ${r.status}`);
  return (await r.json()) as AdminDraft;
}

export async function deleteAdminDraft(draftId: string): Promise<void> {
  const r = await fetch(`${API_BASE}/admin/drafts/${draftId}`, { method: 'DELETE', credentials: 'include' });
  if (!r.ok) throw new Error(`deleteAdminDraft failed: ${r.status}`);
}

export async function validateAdminDraft(draftId: string): Promise<AdminDraftValidation> {
  const r = await fetch(`${API_BASE}/admin/drafts/${draftId}/validation`, { credentials: 'include' });
  if (!r.ok) throw new Error(`validateAdminDraft failed: ${r.status}`);
  return (await r.json()) as AdminDraftValidation;
}

export async function getAdminDraftReviewExport(draftId: string): Promise<AdminDraftReviewExport> {
  const r = await fetch(`${API_BASE}/admin/drafts/${draftId}/review-export`, { credentials: 'include' });
  if (!r.ok) throw new Error(`getAdminDraftReviewExport failed: ${r.status}`);
  return (await r.json()) as AdminDraftReviewExport;
}

export async function getAdminReleaseVersions(): Promise<AdminReleaseVersion[] | null> {
  const r = await fetch(`${API_BASE}/admin/releases`, { credentials: 'include' });
  if (r.status === 401 || r.status === 403) return null;
  if (!r.ok) throw new Error(`getAdminReleaseVersions failed: ${r.status}`);
  return ((await r.json()) as { releases: AdminReleaseVersion[] }).releases;
}

export async function createAdminReleaseVersion(draftId: string): Promise<AdminReleaseVersion> {
  const r = await fetch(`${API_BASE}/admin/drafts/${draftId}/release-versions`, { method: 'POST', credentials: 'include' });
  if (!r.ok) throw new Error(`createAdminReleaseVersion failed: ${r.status}`);
  return (await r.json()) as AdminReleaseVersion;
}

export async function getAdminReleaseVersion(releaseId: string): Promise<AdminReleaseSnapshot> {
  const r = await fetch(`${API_BASE}/admin/releases/${releaseId}`, { credentials: 'include' });
  if (!r.ok) throw new Error(`getAdminReleaseVersion failed: ${r.status}`);
  return (await r.json()) as AdminReleaseSnapshot;
}

export async function selectAdminReleaseVersion(releaseId: string, rollback = false): Promise<AdminReleaseVersion> {
  const action = rollback ? 'rollback' : 'select';
  const r = await fetch(`${API_BASE}/admin/releases/${releaseId}/${action}`, { method: 'POST', credentials: 'include' });
  if (!r.ok) throw new Error(`selectAdminReleaseVersion failed: ${r.status}`);
  return (await r.json()) as AdminReleaseVersion;
}

export async function stageAdminReleaseVersion(releaseId: string): Promise<AdminReleaseVersion> {
  const r = await fetch(`${API_BASE}/admin/releases/${releaseId}/stage`, { method: 'POST', credentials: 'include' });
  if (!r.ok) throw new Error(`stageAdminReleaseVersion failed: ${r.status}`);
  return (await r.json()) as AdminReleaseVersion;
}
export interface StagedReleaseReadiness { releaseId: string; bookId: string; version: number; staged: boolean; featureEnabled: boolean; sessionCount: number; completedSessionCount: number; playerSavesTouched: 0; productionPublished: false; }
export async function getStagedReleaseReadiness(releaseId: string): Promise<StagedReleaseReadiness> {
  const r = await fetch(`${API_BASE}/admin/releases/${releaseId}/staging-readiness`, { credentials: 'include' });
  if (!r.ok) throw new Error(`getStagedReleaseReadiness failed: ${r.status}`);
  return (await r.json()) as StagedReleaseReadiness;
}
export async function configureBetaReleaseAccess(releaseId: string, emails: string[]): Promise<{ enabled: boolean; invitedCount: number }> {
  const r = await fetch(`${API_BASE}/admin/releases/${releaseId}/beta-access`, { method: 'PUT', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ emails }) });
  if (!r.ok) throw new Error(`configureBetaReleaseAccess failed: ${r.status}`);
  return (await r.json()) as { enabled: boolean; invitedCount: number };
}
export async function getBetaReleaseReadiness(releaseId: string): Promise<BetaReadiness> {
  const r = await fetch(`${API_BASE}/admin/releases/${releaseId}/beta-readiness`, { credentials: 'include' });
  if (!r.ok) throw new Error(`getBetaReleaseReadiness failed: ${r.status}`);
  return (await r.json()) as BetaReadiness;
}
export async function getBetaReleaseAccess(releaseId: string): Promise<string[]> {
  const r = await fetch(`${API_BASE}/admin/releases/${releaseId}/beta-access`, { credentials: 'include' });
  if (!r.ok) throw new Error(`getBetaReleaseAccess failed: ${r.status}`);
  return ((await r.json()) as { emails: string[] }).emails;
}
export async function getBetaReleaseFeedback(releaseId: string): Promise<BetaFeedback[]> {
  const r = await fetch(`${API_BASE}/admin/releases/${releaseId}/beta-feedback`, { credentials: 'include' });
  if (!r.ok) throw new Error(`getBetaReleaseFeedback failed: ${r.status}`);
  return ((await r.json()) as { feedback: BetaFeedback[] }).feedback;
}
export async function getBetaReleaseReport(releaseId: string): Promise<BetaReport> {
  const r = await fetch(`${API_BASE}/admin/releases/${releaseId}/beta-report`, { credentials: 'include' });
  if (!r.ok) throw new Error(`getBetaReleaseReport failed: ${r.status}`);
  return (await r.json()) as BetaReport;
}
export async function getBetaReleaseRouteAnalytics(releaseId: string): Promise<BetaRouteAnalytics> {
  const r = await fetch(`${API_BASE}/admin/releases/${releaseId}/beta-route-analytics`, { credentials: 'include' });
  if (!r.ok) throw new Error(`getBetaReleaseRouteAnalytics failed: ${r.status}`);
  return (await r.json()) as BetaRouteAnalytics;
}
export async function triageBetaReleaseFeedback(releaseId: string, feedbackId: string, input: Pick<BetaFeedback, 'status' | 'adminNote'>): Promise<BetaFeedback> {
  const r = await fetch(`${API_BASE}/admin/releases/${releaseId}/beta-feedback/${feedbackId}`, { method: 'PATCH', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input) });
  if (!r.ok) throw new Error(`triageBetaReleaseFeedback failed: ${r.status}`);
  return (await r.json()) as BetaFeedback;
}
export async function recordBetaReleaseDecision(releaseId: string, input: Pick<BetaDecision, 'decision' | 'note'>): Promise<{ releaseId: string; decision: BetaDecision; productionPublished: false }> {
  const r = await fetch(`${API_BASE}/admin/releases/${releaseId}/beta-decision`, { method: 'PUT', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input) });
  if (!r.ok) throw new Error(`recordBetaReleaseDecision failed: ${r.status}`);
  return (await r.json()) as { releaseId: string; decision: BetaDecision; productionPublished: false };
}
export async function approveReleasePublicationReview(releaseId: string, input: Pick<PublicationApproval, 'checksum' | 'note'>): Promise<{ releaseId: string; approval: PublicationApproval; productionPublished: false }> {
  const r = await fetch(`${API_BASE}/admin/releases/${releaseId}/publication-approval`, { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input) });
  if (!r.ok) throw new Error(`approveReleasePublicationReview failed: ${r.status}`);
  return (await r.json()) as { releaseId: string; approval: PublicationApproval; productionPublished: false };
}
export async function getReleasePublicationHandoff(releaseId: string): Promise<PublicationHandoff> {
  const r = await fetch(`${API_BASE}/admin/releases/${releaseId}/publication-handoff`, { credentials: 'include' });
  if (!r.ok) throw new Error(`getReleasePublicationHandoff failed: ${r.status}`);
  return (await r.json()) as PublicationHandoff;
}
export async function getTrustedContentCompatibility(releaseId: string): Promise<TrustedContentCompatibility> {
  const r = await fetch(`${API_BASE}/admin/releases/${releaseId}/trusted-content-compatibility`, { credentials: 'include' });
  if (!r.ok) throw new Error(`getTrustedContentCompatibility failed: ${r.status}`);
  return (await r.json()) as TrustedContentCompatibility;
}
export async function getNarrativeConversionPreview(releaseId: string): Promise<NarrativeConversionPreview> {
  const r = await fetch(`${API_BASE}/admin/releases/${releaseId}/narrative-conversion-preview`, { credentials: 'include' });
  if (!r.ok) throw new Error(`getNarrativeConversionPreview failed: ${r.status}`);
  return (await r.json()) as NarrativeConversionPreview;
}
export async function registerReleaseCatalogueCandidate(releaseId: string): Promise<{ candidate: CatalogueRegistration; productionPublished: false; note: string }> {
  const r = await fetch(`${API_BASE}/admin/releases/${releaseId}/catalogue-registration`, { method: 'POST', credentials: 'include' });
  if (!r.ok) throw new Error(`registerReleaseCatalogueCandidate failed: ${r.status}`);
  return (await r.json()) as { candidate: CatalogueRegistration; productionPublished: false; note: string };
}
export async function getReleaseCatalogueCandidates(): Promise<CatalogueRegistration[]> {
  const r = await fetch(`${API_BASE}/admin/catalogue-candidates`, { credentials: 'include' });
  if (!r.ok) throw new Error(`getReleaseCatalogueCandidates failed: ${r.status}`);
  return ((await r.json()) as { candidates: CatalogueRegistration[] }).candidates;
}
export async function withdrawReleaseCatalogueCandidate(candidateId: string): Promise<{ candidate: CatalogueRegistration; productionPublished: false; note: string }> {
  const r = await fetch(`${API_BASE}/admin/catalogue-candidates/${candidateId}/withdraw`, { method: 'POST', credentials: 'include' });
  if (!r.ok) throw new Error(`withdrawReleaseCatalogueCandidate failed: ${r.status}`);
  return (await r.json()) as { candidate: CatalogueRegistration; productionPublished: false; note: string };
}
export async function getReleaseCatalogueActivationPreflight(candidateId: string): Promise<CatalogueActivationPreflight> {
  const r = await fetch(`${API_BASE}/admin/catalogue-candidates/${candidateId}/activation-preflight`, { credentials: 'include' });
  if (!r.ok) throw new Error(`getReleaseCatalogueActivationPreflight failed: ${r.status}`);
  return (await r.json()) as CatalogueActivationPreflight;
}

export async function getStagedReleasePreview(bookId: string): Promise<StagedReleasePreview | null> {
  const r = await fetch(`${API_BASE}/staged-releases/${encodeURIComponent(bookId)}`);
  if (r.status === 404) return null;
  if (!r.ok) throw new Error(`getStagedReleasePreview failed: ${r.status}`);
  return (await r.json()) as StagedReleasePreview;
}

const stagedTokenHeaders = (sessionToken: string) => ({ 'X-Staged-Preview-Token': sessionToken, 'Content-Type': 'application/json' });
export async function createStagedPreviewSession(bookId: string): Promise<StagedPreviewSession> {
  const r = await fetch(`${API_BASE}/staged-releases/${encodeURIComponent(bookId)}/sessions`, { method: 'POST' });
  if (!r.ok) throw new Error(`createStagedPreviewSession failed: ${r.status}`);
  return (await r.json()) as StagedPreviewSession;
}
export async function getStagedPreviewSession(sessionId: string, sessionToken: string): Promise<StagedPreviewSession> {
  const r = await fetch(`${API_BASE}/staged-preview-sessions/${sessionId}`, { headers: { 'X-Staged-Preview-Token': sessionToken } });
  if (!r.ok) throw new Error(`getStagedPreviewSession failed: ${r.status}`);
  return (await r.json()) as StagedPreviewSession;
}
export async function chooseStagedPreviewSession(sessionId: string, sessionToken: string, payload: { sceneId: string; choiceId: string; baseRevision: number }): Promise<StagedPreviewSession> {
  const r = await fetch(`${API_BASE}/staged-preview-sessions/${sessionId}/choices`, { method: 'POST', headers: stagedTokenHeaders(sessionToken), body: JSON.stringify(payload) });
  if (!r.ok) throw new Error(`chooseStagedPreviewSession failed: ${r.status}`);
  return (await r.json()) as StagedPreviewSession;
}
export async function restartStagedPreviewSession(sessionId: string, sessionToken: string): Promise<StagedPreviewSession> {
  const r = await fetch(`${API_BASE}/staged-preview-sessions/${sessionId}/restart`, { method: 'POST', headers: stagedTokenHeaders(sessionToken) });
  if (!r.ok) throw new Error(`restartStagedPreviewSession failed: ${r.status}`);
  return (await r.json()) as StagedPreviewSession;
}
export async function getBetaReleasePreview(bookId: string): Promise<BetaReleasePreview | null> {
  const r = await fetch(`${API_BASE}/beta-releases/${encodeURIComponent(bookId)}`, { credentials: 'include' });
  if (r.status === 401 || r.status === 403 || r.status === 404) return null;
  if (!r.ok) throw new Error(`getBetaReleasePreview failed: ${r.status}`);
  return (await r.json()) as BetaReleasePreview;
}
export async function createOrResumeBetaSession(bookId: string): Promise<BetaPlayerSession> {
  const r = await fetch(`${API_BASE}/beta-releases/${encodeURIComponent(bookId)}/sessions`, { method: 'POST', credentials: 'include' });
  if (!r.ok) throw new Error(`createOrResumeBetaSession failed: ${r.status}`);
  return (await r.json()) as BetaPlayerSession;
}
export async function chooseBetaSession(sessionId: string, payload: { sceneId: string; choiceId: string; baseRevision: number }): Promise<BetaPlayerSession> {
  const r = await fetch(`${API_BASE}/beta-player-sessions/${sessionId}/choices`, { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
  if (!r.ok) throw new Error(`chooseBetaSession failed: ${r.status}`);
  return (await r.json()) as BetaPlayerSession;
}
export async function restartBetaSession(sessionId: string): Promise<BetaPlayerSession> {
  const r = await fetch(`${API_BASE}/beta-player-sessions/${sessionId}/restart`, { method: 'POST', credentials: 'include' });
  if (!r.ok) throw new Error(`restartBetaSession failed: ${r.status}`);
  return (await r.json()) as BetaPlayerSession;
}
export async function submitBetaFeedback(sessionId: string, message: string): Promise<void> {
  const r = await fetch(`${API_BASE}/beta-player-sessions/${sessionId}/feedback`, { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message }) });
  if (!r.ok) throw new Error(`submitBetaFeedback failed: ${r.status}`);
}

export async function logoutApi(): Promise<void> {
  try { await fetch(`${API_BASE}/auth/logout`, { method: 'POST', credentials: 'include' }); } catch { /* ignore */ }
}

export async function getAccountSave(): Promise<CloudSave | null> {
  const r = await fetch(`${API_BASE}/me/save`, { credentials: 'include' });
  if (r.status === 404) return null;
  if (!r.ok) throw new Error(`getAccountSave failed: ${r.status}`);
  return (await r.json()) as CloudSave;
}

export async function putAccountSave(payload: SavePayload): Promise<PutResult> {
  const r = await fetch(`${API_BASE}/me/save`, {
    method: 'PUT', credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (r.status === 409) {
    const body = await r.json().catch(() => ({}));
    return { ok: false, currentSave: body.currentSave ?? null };
  }
  if (!r.ok) throw new Error(`putAccountSave failed: ${r.status}`);
  return { ok: true, save: (await r.json()) as CloudSave };
}

export type ClaimResult =
  | { ok: true; save: CloudSave }
  | { ok: false; conflict: true; accountSave: CloudSave; anonymousSave: any }
  | { ok: false; error: string };

export async function claimSave(playerId: string, strategy?: 'use_account' | 'use_anonymous'): Promise<ClaimResult> {
  const r = await fetch(`${API_BASE}/me/claim`, {
    method: 'POST', credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ playerId, strategy }),
  });
  if (r.ok) return { ok: true, save: (await r.json()) as CloudSave };
  const body = await r.json().catch(() => ({}));
  if (r.status === 409 && body.error === 'claim_conflict') {
    return { ok: false, conflict: true, accountSave: body.accountSave, anonymousSave: body.anonymousSave };
  }
  return { ok: false, error: (body.detail && body.detail.error) || body.error || `http_${r.status}` };
}
