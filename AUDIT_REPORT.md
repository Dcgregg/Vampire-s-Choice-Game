# Vampire's Choice — Codebase Audit Report

**Date:** 2026-06 · **Scope:** Read-only technical audit. No production architecture, no rebuild, no redesign.
**Verdict:** Healthy, well-structured prototype with a surprisingly production-shaped type system. A handful of correctness bugs, some dead code/dependencies, and the expected "browser-only" scalability & security ceilings. Recommended first move is low-risk and does **not** touch the UI, backend, or design.

---

## A. Current Architecture (plain English)

Vampire's Choice is a **single-page client-only web app**. There is no backend in play at runtime.

- **Framework:** Vite 6 + React 19 + TypeScript, styled with Tailwind CSS v4 (via `@tailwindcss/vite`) and a custom gothic design layer in `index.css`. Icons via `lucide-react`, celebration FX via `canvas-confetti`, ambient sound via the browser's Web Audio API (no audio files).
- **PWA:** `vite-plugin-pwa` provides the manifest + auto-updating service worker; icons live in `public/`.
- **Navigation:** There is **no router**. The app renders one of eight screens based on a single string, `activeScreen`, held in the state manager. `App.tsx` is a big `activeScreen === '...'` switch.
- **State:** A single module-level singleton, `gameStateManager` (an instance of the `GameStateManager` class in `state/gameState.ts`), holds all mutable game state and exposes imperative methods (`makeChoice`, `createCharacter`, `setScreen`, …). A thin React Context (`state/useGameState.tsx`) subscribes to it and re-renders the tree on change.
- **Content:** The entire story lives as static TypeScript objects in `data/story/book1.ts` — one `Book` object plus a flat map of `Scene`s keyed by id.
- **Persistence:** The full state object is JSON-serialized into a single `localStorage` key on every change.

Conceptually it already resembles the target layering (UI → engine → data → state), but the "engine" logic currently lives **inside** the state manager and the reading screen rather than in a standalone module.

---

## B. Current File Structure

```
/app
├── index.html                 # Fonts (Cinzel / Cormorant / Jakarta), theme meta, root div
├── package.json               # Vite scripts; several UNUSED deps (see F)
├── vite.config.ts             # React + Tailwind + PWA plugins, manifest, dev server
├── tsconfig.json              # bundler resolution, path alias "@/*"
├── metadata.json              # AI Studio manifest (declares SERVER_SIDE_GEMINI_API capability)
├── .env.example               # GEMINI_API_KEY / APP_URL placeholders (AI Studio convention)
├── bun.lock                   # lockfile from AI Studio (bun); repo now runs under yarn here
├── public/                    # PWA icons (192/512/maskable), apple-touch, icon.svg
└── src/
    ├── main.tsx               # React root
    ├── App.tsx                # Screen switch + global overlays
    ├── index.css              # Gothic design system (fonts, scrollbar, glows, vignette)
    ├── types/index.ts         # ★ All domain types (Scene/Choice/Effect/Condition/Player…)
    ├── state/
    │   ├── gameState.ts       # ★ GameStateManager singleton + game logic
    │   └── useGameState.tsx   # React Context bridge + pub/sub subscription
    ├── data/
    │   ├── characters.ts      # INITIAL_CHARACTERS (4 characters)
    │   ├── achievements.ts    # INITIAL_ACHIEVEMENTS (6 achievements)
    │   └── story/
    │       ├── index.ts       # BOOKS registry, ALL_SCENES map, getSceneById/getBookById
    │       └── book1.ts       # ★ Book 1: 3 chapters, ~14 scenes, all choices/effects
    ├── utils/
    │   ├── storage.ts         # localStorage load/save/clear + DEFAULT_PLAYER_STATE
    │   └── audio.ts           # Procedural gothic soundscape (Web Audio)
    ├── hooks/
    │   ├── useOnlineStatus.ts # navigator.onLine listener
    │   └── usePWAInstall.ts   # beforeinstallprompt + iOS detection
    └── components/
        ├── common/            # Navbar, BottomNav, AchievementBanner, ConsequenceToast,
        │                        OfflineIndicator, PWAInstallButton
        └── screens/           # Landing, CharacterCreation, Reading, Character,
                                 Relationships, Achievements, Settings, About
```

★ = the four files that carry the product's real substance.

---

## C. Current Data Model

All types live in `types/index.ts`. The model is **declarative and already close to the desired engine shape** — this is the codebase's biggest asset.

**PlayerState (the single saved blob):**
```
PlayerState {
  player: PlayerProfile | null      // name, genderIdentity, sexualOrientation, createdAt
  relationships: { [charId]: Character }
  flags: StoryFlagMap               // { key: boolean | string | number }
  progress: PlayerProgress          // currentBookId, currentChapter, currentSceneId,
                                     //   completedChapters[], sceneHistory[]
  bloodCoins: number                // virtual currency
  dailyStreak: number
  lastLoginDate: string
  achievements: { [id]: Achievement }
  settings: GameSettings            // fontSize, ambientAudio, reducedMotion, highContrast
  version: number                   // = 1 (no migration code exists yet)
}
```

**Character / Relationship:** `{ id, name, title, description, avatar, affinity (0–100), romanceEligible, status, loreUnlocked[] }`. `status` is derived from `affinity` via `updateRelationshipStatus()` (Rival ≤25, Acquaintance <50, Intrigued <65, Trusted <85, Devoted ≥85).

**Story content:**
```
Book → Chapter[] (number, title, summary, firstSceneId, totalScenes,
                  rewardCoins, completionAchievementId)
Scene {
  id, bookId, chapterNumber/Title, sceneTitle, sceneIndex,
  paragraphs[],
  dialogues?[]          // speaker, text, characterId, mood
  conditionParagraphs?[]// conditionFlag (+ expectedValue) → paragraphs[]  ← EVALUATED
  choices: SceneChoice[]
  atmosphere?           // ambientColor, soundFx, quoteBanner
  audioUrl?/voiceId?/audioStatus?  // placeholders reserved for future TTS
}
SceneChoice {
  id, text, nextSceneId,
  consequencesSummary?,
  effects?: ChoiceEffect  // relationshipChanges, setFlags, coinsChange,
                          //   streakIncrement, achievementId, notificationText
  condition?: ChoiceCondition  // requiredFlags, minRelationship  ← DEFINED BUT NEVER USED
  isRomantic?/isDangerous?
}
```

**Achievement:** `{ id, title, description, iconName, unlockedAt?, isSecret?, rarity }`.

---

## D. Current Story Engine — exactly how a player progresses

1. On mount, `loadSavedState()` hydrates state from localStorage (shallow-merged over `DEFAULT_PLAYER_STATE`).
2. Character creation sets `progress.currentSceneId = 'b1_c1_s1'` and switches `activeScreen` to `reading`.
3. `ReadingScreen` looks up the scene with `getSceneById(currentSceneId)` and renders: header → drop-capped narrative paragraphs → any **conditionParagraphs** whose `conditionFlag` matches current flags → dialogues (with live affinity badges) → the choice buttons. All choices are rendered **unconditionally**.
4. When the player taps a choice, `gameStateManager.makeChoice(choice)` runs imperatively:
   - plays a chime;
   - applies `effects.relationshipChanges` (clamped 0–100, status recomputed; unlocks `DANGEROUS_LIAISON` if any affinity ≥70);
   - merges `effects.setFlags` into `flags`;
   - adds `effects.coinsChange` to `bloodCoins` (floored at 0);
   - unlocks `effects.achievementId` if present;
   - shows a consequence toast from `notificationText`;
   - then advances: `currentSceneId = choice.nextSceneId`, pushes to `sceneHistory`, updates `currentChapter`.
5. `notify()` saves state and re-renders. Scroll resets to top on scene change.

**Key point:** the "next scene" is a **hardcoded `nextSceneId` on each choice**. There is no runtime branch resolution and **no condition evaluation for choices** (the `ChoiceCondition` type exists but nothing reads it). Only *paragraph*-level conditions are honored. Branching is therefore entirely author-wired per choice.

---

## E. Current Persistence — exactly how progress is saved

- **Store:** one localStorage key, `vampires_choice_player_state_v1`.
- **When:** `savePlayerState()` runs inside `notify()`, which fires on **every** state change — including pure navigation (`setScreen`). So merely tapping a nav tab rewrites the entire save blob.
- **What survives refresh:** everything in `PlayerState` (player, flags, relationships, coins, achievements, progress, settings). `activeScreen` is **not** part of `PlayerState` and is not saved, so a refresh always returns to the Landing screen; "Continue Story" then resumes from `currentSceneId`.
- **Load robustness:** `loadSavedState()` wraps parse in try/catch and shallow-merges saved data over defaults so missing top-level fields don't crash. There is **no versioned migration** logic despite the `version` field.
- **Reset:** Settings → Reset clears the key and reinstates defaults.

---

## F. Problems / Technical Debt

### 🔴 Critical
1. **Exposed GitHub credential in the git remote.** The `origin` remote URL embeds a GitHub access token in plaintext. Anyone with repo/pod access can read it and push as the owner. **Revoke & rotate immediately** (see Security §12), then set the remote to a tokenless HTTPS or SSH URL and use a credential helper. Never embed tokens in remote URLs.

### 🟠 Important
2. **`ChoiceCondition` is dead code.** `requiredFlags` / `minRelationship` are declared but never evaluated, so conditional/locked choices are impossible today. This is the single biggest gap between the current engine and the "conditions → choices" principle in the brief.
3. **Fake daily streak.** `dailyStreak` defaults to `3` and is displayed in three places, but `checkDailyStreak()` only updates `lastLoginDate` — it never increments or resets the streak. `effects.streakIncrement` is likewise never handled.
4. **`completedChapters` is never populated.** It's initialized to `[]` and never appended to; chapter completion is tracked ad-hoc via story flags (`completedChapter1`, etc.). Two competing sources of truth.
5. **Book-1 ending loops to scene 1.** The final choice (`c3_3_conclude_book1`) sets `nextSceneId: 'b1_c1_s1'`, so "completing" the book silently drops the player back at the opening scene with all flags intact — a confusing dead-end. There is no dedicated "book complete" screen.
6. **Duplicated reward logic.** `Chapter.rewardCoins` / `Chapter.completionAchievementId` are decorative; the actual coins/achievements are hardcoded again inside each choice's `effects`. Easy to drift out of sync.
7. **Dead dependencies shipped.** `@google/genai`, `motion`, `express`, and `dotenv` are in `package.json` but **imported nowhere** in `src/`. They inflate install size and, in `@google/genai`'s case, hint at an AI path that could later leak keys client-side. Remove when convenient.

### 🟢 Nice to have
8. **Save-on-navigation.** Persisting the whole blob on every `setScreen` is wasteful (harmless at this size). A tiny debounce or saving only on meaningful mutations would be cleaner.
9. **No content validation.** Story data is hand-authored TS; a typo in a `nextSceneId` fails silently to the "shadows have closed" fallback. A schema check (e.g. zod) would catch dangling links.
10. **Character base-data migration gap.** `loadSavedState` replaces each saved character object wholesale, so new `loreUnlocked`/titles added to `INITIAL_CHARACTERS` won't reach existing players.
11. **Emoji used as character icons** in dialogue/relationship views (🦇🧪📜🕯️) — cosmetically fine, but a themed SVG/lucide set would read as more premium and is more controllable.
12. **`bun.lock` present but the environment runs `yarn`.** Pick one package manager to keep lockfiles authoritative.

---

## G. Scalability Risks (at thousands of users / hundreds of scenes / multiple books)

- **Content in code.** A flat scene map in a `.ts` file does not scale to hundreds of scenes or multiple books, and cannot be edited by non-developers. Needs a data-driven content store and, later, a CMS.
- **Author-wired branching.** With no condition engine, every path must be hand-linked via `nextSceneId`. Complex branching (the brief's explicit requirement) becomes combinatorially unmanageable.
- **Single global mutable singleton.** Fine for one local player; it blocks multi-user, SSR, isolated testing, and invites races once anything async (network) is introduced.
- **localStorage ceiling.** ~5 MB, single device, single save slot, wiped with browser data, no accounts, no cross-device sync. **The multi-book "persistent state across books" requirement cannot be met on localStorage across devices.**
- **No migrations.** `version` exists but there's no upgrade path; schema changes risk corrupting existing saves.
- **Whole-tree re-render.** One context re-renders all subscribers on any change. Negligible now; will matter as screens/lists grow.
- **Fonts via CDN.** Google Fonts aren't precached, so the "offline" PWA falls back to system fonts offline.

---

## H. Recommended Production Architecture (proposal only — NOT to be implemented yet)

Keep the player frontend (Vite + React) and the gothic design **exactly as-is**. Evolve the layers behind it:

```
        PLAYER (React UI — unchanged gothic experience)
              │  (renders scenes, dispatches choices — no game logic)
              ▼
        STORY ENGINE  (pure, framework-agnostic TypeScript module)
              │  resolveScene(state) · evaluate conditions · apply effects · pick next
              ▼
        CONTENT  (validated data: Series → Book → Chapter → Scene → Choice)
              │  bundled JSON now → served by backend/CMS later
              ▼
        PLAYER STATE  (local cache now → server-authoritative later)
```

- **Extract the engine** out of `GameStateManager`/`ReadingScreen` into a pure module with unit tests. Make it *actually* honor `ChoiceCondition`. This alone unlocks real branching and is behavior-preserving.
- **Content as validated data**, decoupled from React, with a zod schema and a link-integrity check.
- **Backend on Emergent's native stack (FastAPI + MongoDB)** when persistence is needed: player profiles, cloud save/sync, and **server-authoritative currency & achievements**. localStorage becomes an offline/anonymous cache that syncs up.
- **Multi-book** via a single persistent player profile + a shared cross-book flag/variable namespace that Book 2 can read without importing Book 1's logic.
- **Admin CMS + AI authoring** as a *separate* app with its own design language, added much later, with mandatory human review before any AI content is published.
- Auth, payments, TTS, analytics: deferred to their own phases.

---

## Recommended Development Phases

1. **Stabilize & document (now).** This audit; fix the small correctness bugs (streak, book-end loop, `completedChapters`), remove dead deps. Low risk, no UI/design change.
2. **Extract a pure Story Engine + enforce `choice.condition`.** Move logic out of the UI/state singleton into a tested module; keep behavior identical, then enable conditional choices. Add zod content validation.
3. **Externalize content to validated JSON** with a loader and content versioning (still bundled — no backend yet).
4. **Introduce the backend (FastAPI + MongoDB):** anonymous cloud save + sync; make currency & achievements server-authoritative.
5. **Accounts / authentication** (JWT or Google — decided then).
6. **Multi-book persistent cross-book state.**
7. **Admin CMS** (separate design language).
8. **AI-assisted authoring** with human-in-the-loop approval (never auto-publish).
9. **Monetization (server-authoritative), paid audio narration, analytics.**

---

## What I Recommend We Build FIRST

**Phase 2: extract the story engine into a standalone, unit-tested module and make `choice.condition` actually work — bundled with the small Phase-1 bug fixes.**

Why first:
- It is the highest-value, lowest-risk step. It touches **no** UI, **no** design, **no** backend, adds **no** dependencies users can see, and is fully reversible.
- It directly delivers the brief's core "Scene → Conditions → Choices → Effects → Next Scene" principle, which is currently only half-implemented (paragraph conditions work; choice conditions don't).
- Everything else — content externalization, CMS, AI authoring, multi-book — depends on a clean, testable engine existing first. Building the backend or CMS before the engine is decoupled would bake the current coupling into the platform.

Awaiting your approval before making any architectural changes.

---

### Appendix — Environment notes (this preview)
- Installed dependencies with `yarn` and ran Vite on port 3000; the app is live in the preview.
- One preview-only change was required: added `allowedHosts: true` (plus explicit `host`/`port`) to the `server` block in `vite.config.ts` so the Emergent preview domain isn't rejected by Vite's host check. This affects the dev server only, not the production build.
