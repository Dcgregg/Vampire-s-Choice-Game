# Vampire's Choice — PRD / Working Memory

## Original problem statement
Existing-project handover. Vampire's Choice is an episodic gothic-fantasy romance CYOA, prototyped in Google AI Studio and exported to GitHub. Task #1 is a **read-only technical audit** and a development plan — explicitly NOT a rebuild, redesign, backend, auth, DB, payments, AI, TTS, or CMS. Preserve the gothic visual identity. Wait for approval before major architectural changes.

## Tech stack (as found)
Vite 6 + React 19 + TypeScript · Tailwind CSS v4 · vite-plugin-pwa · lucide-react · canvas-confetti · Web Audio (procedural). Client-only SPA; no backend at runtime. Persistence = single localStorage key. No router (screen switch via `activeScreen`). State = module singleton `GameStateManager` + React Context.

## Key files
- `src/types/index.ts` — domain types (Scene/Choice/Effect/Condition/Player…)
- `src/state/gameState.ts` — singleton state manager + all game logic
- `src/state/useGameState.tsx` — Context bridge / pub-sub
- `src/data/story/book1.ts` — Book 1 (3 chapters, ~14 scenes)
- `src/data/characters.ts`, `src/data/achievements.ts`
- `src/utils/storage.ts` (localStorage), `src/utils/audio.ts` (Web Audio)
- `src/components/screens/*`, `src/components/common/*`

## Status
- 2026-06: Completed full read-only audit. App installed (yarn) and running live on port 3000 in preview. Full report at `/app/AUDIT_REPORT.md`. **No feature/logic code changed.** Only preview-enabling change: `allowedHosts: true` + host/port in `vite.config.ts` dev server block.

## Confirmed findings (verified by grep)
- Dead deps (imported nowhere): `@google/genai`, `motion`, `express`, `dotenv`.
- `ChoiceCondition` (requiredFlags/minRelationship) defined but never evaluated → no conditional choices.
- `dailyStreak` never incremented (hardcoded 3); `effects.streakIncrement` never handled.
- `completedChapters` never populated.
- Book-1 ending choice loops `nextSceneId` back to `b1_c1_s1`.
- CRITICAL security: GitHub token embedded in git `origin` remote URL — must be revoked/rotated.
- No frontend key leak in `src/` today (no process.env/GEMINI usage).

## Recommended phases (proposed, awaiting approval)
1. Stabilize + fix small bugs (streak, book-end loop, completedChapters), drop dead deps.
2. **FIRST BUILD:** extract pure, tested Story Engine + enforce `choice.condition`; add zod content validation.
3. Externalize content to validated JSON + versioning (still bundled).
4. Backend (FastAPI + MongoDB): cloud save/sync, server-authoritative currency/achievements.
5. Accounts/auth. 6. Multi-book cross-book state. 7. Admin CMS (separate design). 8. AI authoring (human-in-loop). 9. Monetization/audio/analytics.

## Backlog / do-not-do-yet (per brief)
Production DB, auth, payments, AI APIs, TTS, admin CMS, offline architecture — all deferred until explicitly approved.
