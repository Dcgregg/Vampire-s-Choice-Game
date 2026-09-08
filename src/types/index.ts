/**
 * Vampire's Choice - Core Type Definitions
 */

export type GenderIdentity = 
  | 'Woman'
  | 'Man'
  | 'Non-binary'
  | 'Other'
  | 'Prefer not to say';

export type SexualOrientation = 
  | 'Straight'
  | 'Gay'
  | 'Lesbian'
  | 'Bisexual'
  | 'Pansexual'
  | 'Asexual'
  | 'Other'
  | 'Prefer not to say';

export interface PlayerProfile {
  name: string;
  genderIdentity: GenderIdentity;
  sexualOrientation: SexualOrientation;
  avatarSeed?: string;
  createdAt: number;
}

export interface Character {
  id: string;
  name: string;
  title: string;
  description: string;
  avatar: string; // SVG icon identifier or stylized visual token
  affinity: number; // 0 to 100
  romanceEligible: boolean;
  status: 'Unknown' | 'Acquaintance' | 'Intrigued' | 'Trusted' | 'Devoted' | 'Rival';
  loreUnlocked: string[];
}

export interface StoryFlagMap {
  [key: string]: boolean | string | number;
}

export interface ChoiceEffect {
  relationshipChanges?: { [characterId: string]: number };
  setFlags?: { [flagKey: string]: boolean | string | number };
  coinsChange?: number;
  streakIncrement?: boolean;
  achievementId?: string;
  notificationText?: string;
}

export interface RelationshipThreshold {
  characterId: string;
  min?: number;
  max?: number;
}

/**
 * Declarative conditions attached to a choice (or, in future, content).
 * All present fields must be satisfied simultaneously (logical AND).
 * An undefined/empty condition is always available.
 */
export interface ChoiceCondition {
  // Flags: every listed flag must strictly equal the expected value.
  requiredFlags?: { [flagKey: string]: boolean | string | number };
  // Legacy single relationship threshold (preserved for backwards compatibility).
  minRelationship?: { characterId: string; minValue: number };
  // Foundation: multiple relationship thresholds (min and/or max affinity).
  relationships?: RelationshipThreshold[];
  // Currency / numeric variable bounds.
  minCoins?: number;
  maxCoins?: number;
  // Story progress.
  requiredBook?: string;
  requiredChapter?: number; // player's currentChapter must be >= this
  visitedScene?: string; // sceneHistory must include this scene id
  // Player identity / character properties (where already supported).
  playerGender?: GenderIdentity | GenderIdentity[];
  playerOrientation?: SexualOrientation | SexualOrientation[];
}

export interface SceneChoice {
  id: string;
  text: string;
  nextSceneId: string;
  consequencesSummary?: string;
  effects?: ChoiceEffect;
  condition?: ChoiceCondition;
  isRomantic?: boolean;
  isDangerous?: boolean;
  // When true, selecting this choice ends the current flow and returns the
  // player to the landing screen instead of navigating to another scene.
  // Used for book-ending choices so the story does not silently loop.
  returnToLanding?: boolean;
}

export interface Scene {
  id: string;
  bookId: string;
  chapterNumber: number;
  chapterTitle: string;
  sceneTitle: string;
  sceneIndex: number;
  paragraphs: string[];
  dialogues?: {
    speaker: string;
    text: string;
    characterId?: string;
    mood?: 'neutral' | 'intense' | 'whisper' | 'romantic' | 'warning';
  }[];
  conditionParagraphs?: {
    conditionFlag: string;
    expectedValue?: boolean | string | number;
    paragraphs: string[];
  }[];
  choices: SceneChoice[];
  atmosphere?: {
    ambientColor?: string;
    soundFx?: 'rain' | 'library' | 'heartbeat' | 'ballroom' | 'wind';
    quoteBanner?: string;
  };
  // Future extensibility for TTS / Audio Narration
  audioUrl?: string;
  audioDuration?: number;
  voiceId?: string;
  audioStatus?: 'ready' | 'pending' | 'unavailable';
}

export interface Chapter {
  number: number;
  title: string;
  summary: string;
  firstSceneId: string;
  totalScenes: number;
  rewardCoins: number;
  completionAchievementId?: string;
}

export interface Book {
  id: string;
  title: string;
  subtitle: string;
  synopsis: string;
  chapters: Chapter[];
  coverArtStyle: string;
}

export interface Achievement {
  id: string;
  title: string;
  description: string;
  iconName: string;
  unlockedAt?: number;
  isSecret?: boolean;
  rarity: 'Common' | 'Rare' | 'Gothic Legend';
}

export interface GameSettings {
  fontSize: 'normal' | 'large' | 'xlarge';
  ambientAudio: boolean;
  reducedMotion: boolean;
  highContrast: boolean;
}

export interface PlayerProgress {
  currentBookId: string;
  currentChapter: number;
  currentSceneId: string;
  completedChapters: number[];
  sceneHistory: string[];
}

export interface PlayerState {
  player: PlayerProfile | null;
  relationships: { [characterId: string]: Character };
  flags: StoryFlagMap;
  progress: PlayerProgress;
  bloodCoins: number;
  dailyStreak: number;
  lastLoginDate: string;
  achievements: { [achievementId: string]: Achievement };
  settings: GameSettings;
  version: number;
}
