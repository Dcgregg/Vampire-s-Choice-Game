import {
  PlayerState,
  PlayerProfile,
  GenderIdentity,
  SexualOrientation,
  SceneChoice,
  GameSettings,
} from '../types';
import { loadSavedState, savePlayerState, DEFAULT_PLAYER_STATE, clearPlayerState, migrateAndMerge } from '../utils/storage';
import { getSceneById, ALL_SCENES, BOOKS, BOOK_VERSIONS } from '../data/story';
import { INITIAL_CHARACTERS } from '../data/characters';
import { INITIAL_ACHIEVEMENTS } from '../data/achievements';
import { gothicAudio } from '../utils/audio';
import {
  selectChoice,
  unlockAchievement as engineUnlockAchievement,
  computeDailyStreak,
  updateRelationshipStatus,
  validateContent,
  isCurrentBookCompleted,
  EngineEvent,
} from '../engine';
import { syncManager } from '../sync/syncManager';
import { trustedProgressionQueue } from '../progression/trustedProgressionQueue';

// Re-exported for backwards compatibility with existing imports.
export { updateRelationshipStatus };

export type ScreenType =
  | 'landing'
  | 'character_creation'
  | 'reading'
  | 'book_complete'
  | 'character'
  | 'relationships'
  | 'achievements'
  | 'settings'
  | 'about';

export interface ConsequenceEvent {
  id: string;
  message: string;
  type: 'relationship' | 'flag' | 'currency' | 'secret';
  timestamp: number;
}

export class GameStateManager {
  private state: PlayerState;
  private listeners: Set<() => void> = new Set();
  public activeScreen: ScreenType = 'landing';
  public latestConsequence: ConsequenceEvent | null = null;
  public newlyUnlockedAchievement: PlayerState['achievements'][string] | null = null;

  constructor() {
    this.state = loadSavedState();
    this.checkDailyStreak();

    // Surface content integrity problems early during development.
    if (import.meta.env?.DEV) {
      const issues = validateContent({
        scenes: ALL_SCENES,
        books: BOOKS,
        achievements: INITIAL_ACHIEVEMENTS,
        characters: INITIAL_CHARACTERS,
      });
      if (issues.length) {
        console.warn('[Vampire\u2019s Choice] content validation issues:', issues);
      }
    }

    // Local-first cloud sync sits ABOVE local persistence and never blocks play.
    syncManager.attach({
      getState: () => this.state,
      applyCloudState: (state) => {
        this.state = state;
        this.notify();
      },
      migrate: (raw) => migrateAndMerge(raw),
    });
    void syncManager.start();
  }

  public getState(): PlayerState {
    return this.state;
  }

  public subscribe(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private notify() {
    savePlayerState(this.state);
    this.listeners.forEach((l) => l());
    syncManager.recordLocalSave();
  }

  /** Translate pure engine events into UI side-effects (audio, banner, toast). */
  private handleEvents(events: EngineEvent[]) {
    for (const ev of events) {
      if (ev.type === 'achievementUnlocked') {
        this.newlyUnlockedAchievement = ev.achievement;
        gothicAudio.playAchievementChime();
      } else if (ev.type === 'consequence') {
        this.latestConsequence = {
          id: String(Date.now()),
          message: ev.message,
          type: 'relationship',
          timestamp: Date.now(),
        };
      }
    }
  }

  private checkDailyStreak() {
    const result = computeDailyStreak(this.state);
    if (result.changed) {
      this.state = {
        ...this.state,
        dailyStreak: result.dailyStreak,
        lastLoginDate: result.lastLoginDate,
      };
      savePlayerState(this.state);
    }
  }

  public setScreen(screen: ScreenType) {
    this.activeScreen = screen;
    this.notify();
  }

  public createCharacter(
    name: string,
    genderIdentity: GenderIdentity,
    sexualOrientation: SexualOrientation
  ) {
    const trimmedName = name.trim() || 'Elena';
    const profile: PlayerProfile = {
      name: trimmedName,
      genderIdentity,
      sexualOrientation,
      createdAt: Date.now(),
    };

    this.state = {
      ...this.state,
      player: profile,
      progress: {
        currentBookId: 'book1',
        currentChapter: 1,
        currentSceneId: 'b1_c1_s1',
        completedChapters: [],
        completedBooks: [],
        sceneHistory: ['b1_c1_s1'],
      },
      contentVersions: { ...BOOK_VERSIONS },
    };

    this.unlockAchievement('THE_STORY_BEGINS');

    this.activeScreen = 'reading';
    this.notify();
  }

  public continueStory() {
    if (this.state.player && this.state.progress.currentSceneId) {
      // A finished book must not reopen its finale as though unfinished.
      this.activeScreen = isCurrentBookCompleted(this.state) ? 'book_complete' : 'reading';
    } else {
      this.activeScreen = 'character_creation';
    }
    this.notify();
  }

  public unlockAchievement(achievementId: string) {
    const { state, event } = engineUnlockAchievement(this.state, achievementId);
    if (event) {
      this.state = state;
      this.newlyUnlockedAchievement = event.achievement;
      gothicAudio.playAchievementChime();
      this.notify();
    }
  }

  public dismissAchievementBanner() {
    this.newlyUnlockedAchievement = null;
    this.notify();
  }

  public clearConsequenceToast() {
    this.latestConsequence = null;
    this.notify();
  }

  public makeChoice(choice: SceneChoice) {
    const result = selectChoice(this.state, choice, getSceneById);

    // A choice whose conditions are not satisfied is not executable.
    if (!result.ok) return;

    const bookId = this.state.progress.currentBookId;
    const contentVersion = this.state.contentVersions?.[bookId];
    if (!trustedProgressionQueue.recordChoice({
      bookId,
      contentVersion: contentVersion ?? -1,
      fromSceneId: this.state.progress.currentSceneId,
      choiceId: choice.id,
    })) return;

    gothicAudio.playChoiceChime();
    this.state = result.state;
    this.handleEvents(result.events);

    if (result.bookCompleted) {
      this.activeScreen = 'book_complete';
    }

    this.notify();
  }

  public jumpToScene(sceneId: string) {
    const scene = getSceneById(sceneId);
    if (scene) {
      this.state = {
        ...this.state,
        progress: {
          ...this.state.progress,
          currentSceneId: scene.id,
          currentChapter: scene.chapterNumber,
        },
      };
      this.notify();
    }
  }

  public updateSettings(newSettings: Partial<GameSettings>) {
    this.state = {
      ...this.state,
      settings: { ...this.state.settings, ...newSettings },
    };
    if (newSettings.ambientAudio !== undefined) {
      if (newSettings.ambientAudio) {
        gothicAudio.playAtmosphere();
      } else {
        gothicAudio.stopAtmosphere();
      }
    }
    this.notify();
  }

  public interpolate(text: string): string {
    const name = this.state.player?.name || 'Scholar';
    return text.replace(/\[NAME\]/g, name);
  }

  public resetAllData() {
    clearPlayerState();
    this.state = {
      ...DEFAULT_PLAYER_STATE,
      relationships: { ...DEFAULT_PLAYER_STATE.relationships },
      achievements: { ...DEFAULT_PLAYER_STATE.achievements },
      flags: {},
      progress: { ...DEFAULT_PLAYER_STATE.progress },
    };
    this.activeScreen = 'landing';
    this.latestConsequence = null;
    this.newlyUnlockedAchievement = null;
    gothicAudio.stopAtmosphere();
    this.notify();
  }
}

export const gameStateManager = new GameStateManager();
