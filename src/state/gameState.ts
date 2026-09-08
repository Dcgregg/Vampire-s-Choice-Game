import {
  PlayerState,
  PlayerProfile,
  GenderIdentity,
  SexualOrientation,
  SceneChoice,
  GameSettings,
  Achievement,
} from '../types';
import { loadSavedState, savePlayerState, DEFAULT_PLAYER_STATE, clearPlayerState } from '../utils/storage';
import { getSceneById } from '../data/story';
import { gothicAudio } from '../utils/audio';

export type ScreenType =
  | 'landing'
  | 'character_creation'
  | 'reading'
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

export function updateRelationshipStatus(affinity: number): 'Unknown' | 'Acquaintance' | 'Intrigued' | 'Trusted' | 'Devoted' | 'Rival' {
  if (affinity <= 25) return 'Rival';
  if (affinity < 50) return 'Acquaintance';
  if (affinity < 65) return 'Intrigued';
  if (affinity < 85) return 'Trusted';
  return 'Devoted';
}

export class GameStateManager {
  private state: PlayerState;
  private listeners: Set<() => void> = new Set();
  public activeScreen: ScreenType = 'landing';
  public latestConsequence: ConsequenceEvent | null = null;
  public newlyUnlockedAchievement: Achievement | null = null;

  constructor() {
    this.state = loadSavedState();
    // If player already created and was in reading progress, land screen can offer continue
    this.checkDailyStreak();
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
  }

  private checkDailyStreak() {
    const today = new Date().toISOString().split('T')[0];
    if (this.state.lastLoginDate !== today) {
      // In prototype: update last login and simulate streak increment
      this.state.lastLoginDate = today;
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

    this.state.player = profile;
    this.state.progress = {
      currentBookId: 'book1',
      currentChapter: 1,
      currentSceneId: 'b1_c1_s1',
      completedChapters: [],
      sceneHistory: ['b1_c1_s1'],
    };

    // Unlock THE_STORY_BEGINS achievement
    this.unlockAchievement('THE_STORY_BEGINS');

    this.activeScreen = 'reading';
    this.notify();
  }

  public continueStory() {
    if (this.state.player && this.state.progress.currentSceneId) {
      this.activeScreen = 'reading';
      this.notify();
    } else {
      this.activeScreen = 'character_creation';
      this.notify();
    }
  }

  public unlockAchievement(achievementId: string) {
    const ach = this.state.achievements[achievementId];
    if (ach && !ach.unlockedAt) {
      ach.unlockedAt = Date.now();
      this.state.achievements[achievementId] = { ...ach };
      this.newlyUnlockedAchievement = ach;
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
    gothicAudio.playChoiceChime();

    // 1. Process effects
    if (choice.effects) {
      const {
        relationshipChanges,
        setFlags,
        coinsChange,
        achievementId,
        notificationText,
      } = choice.effects;

      // Relationships
      if (relationshipChanges) {
        Object.entries(relationshipChanges).forEach(([charId, delta]) => {
          const char = this.state.relationships[charId];
          if (char) {
            const newAffinity = Math.max(0, Math.min(100, char.affinity + delta));
            char.affinity = newAffinity;
            char.status = updateRelationshipStatus(newAffinity);

            // Check Dangerous Liaison achievement if affinity >= 70
            if (newAffinity >= 70) {
              this.unlockAchievement('DANGEROUS_LIAISON');
            }
          }
        });
      }

      // Flags
      if (setFlags) {
        this.state.flags = {
          ...this.state.flags,
          ...setFlags,
        };
      }

      // Currency
      if (coinsChange) {
        this.state.bloodCoins = Math.max(0, this.state.bloodCoins + coinsChange);
      }

      // Achievement
      if (achievementId) {
        this.unlockAchievement(achievementId);
      }

      // Notification
      if (notificationText) {
        this.latestConsequence = {
          id: String(Date.now()),
          message: notificationText,
          type: 'relationship',
          timestamp: Date.now(),
        };
      }
    }

    // 2. Advance to next scene
    const targetScene = getSceneById(choice.nextSceneId);
    if (targetScene) {
      this.state.progress.currentSceneId = targetScene.id;
      this.state.progress.currentChapter = targetScene.chapterNumber;
      if (!this.state.progress.sceneHistory.includes(targetScene.id)) {
        this.state.progress.sceneHistory.push(targetScene.id);
      }
    }

    this.notify();
  }

  public jumpToScene(sceneId: string) {
    const scene = getSceneById(sceneId);
    if (scene) {
      this.state.progress.currentSceneId = scene.id;
      this.state.progress.currentChapter = scene.chapterNumber;
      this.notify();
    }
  }

  public updateSettings(newSettings: Partial<GameSettings>) {
    this.state.settings = {
      ...this.state.settings,
      ...newSettings,
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
