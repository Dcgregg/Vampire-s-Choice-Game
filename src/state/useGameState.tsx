import React, { createContext, useContext, useEffect, useState, useMemo } from 'react';
import { gameStateManager, ScreenType, ConsequenceEvent } from './gameState';
import { PlayerState, SceneChoice, GameSettings, GenderIdentity, SexualOrientation } from '../types';

interface GameStateContextType {
  state: PlayerState;
  activeScreen: ScreenType;
  latestConsequence: ConsequenceEvent | null;
  newlyUnlockedAchievement: PlayerState['achievements'][string] | null;
  setScreen: (screen: ScreenType) => void;
  createCharacter: (name: string, gender: GenderIdentity, orientation: SexualOrientation) => void;
  continueStory: () => void;
  makeChoice: (choice: SceneChoice) => void;
  jumpToScene: (sceneId: string) => void;
  updateSettings: (settings: Partial<GameSettings>) => void;
  interpolate: (text: string) => string;
  dismissAchievementBanner: () => void;
  clearConsequenceToast: () => void;
  resetAllData: () => void;
}

const GameStateContext = createContext<GameStateContextType | null>(null);

export const GameStateProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [state, setState] = useState<PlayerState>(gameStateManager.getState());
  const [activeScreen, setActiveScreen] = useState<ScreenType>(gameStateManager.activeScreen);
  const [latestConsequence, setLatestConsequence] = useState<ConsequenceEvent | null>(
    gameStateManager.latestConsequence
  );
  const [newlyUnlockedAchievement, setNewlyUnlockedAchievement] = useState(
    gameStateManager.newlyUnlockedAchievement
  );

  useEffect(() => {
    const unsubscribe = gameStateManager.subscribe(() => {
      setState({ ...gameStateManager.getState() });
      setActiveScreen(gameStateManager.activeScreen);
      setLatestConsequence(gameStateManager.latestConsequence);
      setNewlyUnlockedAchievement(gameStateManager.newlyUnlockedAchievement);
    });
    return unsubscribe;
  }, []);

  const value = useMemo(
    () => ({
      state,
      activeScreen,
      latestConsequence,
      newlyUnlockedAchievement,
      setScreen: (s: ScreenType) => gameStateManager.setScreen(s),
      createCharacter: (name: string, g: GenderIdentity, o: SexualOrientation) =>
        gameStateManager.createCharacter(name, g, o),
      continueStory: () => gameStateManager.continueStory(),
      makeChoice: (c: SceneChoice) => gameStateManager.makeChoice(c),
      jumpToScene: (id: string) => gameStateManager.jumpToScene(id),
      updateSettings: (st: Partial<GameSettings>) => gameStateManager.updateSettings(st),
      interpolate: (txt: string) => gameStateManager.interpolate(txt),
      dismissAchievementBanner: () => gameStateManager.dismissAchievementBanner(),
      clearConsequenceToast: () => gameStateManager.clearConsequenceToast(),
      resetAllData: () => gameStateManager.resetAllData(),
    }),
    [state, activeScreen, latestConsequence, newlyUnlockedAchievement]
  );

  return <GameStateContext.Provider value={value}>{children}</GameStateContext.Provider>;
};

export function useGameState(): GameStateContextType {
  const ctx = useContext(GameStateContext);
  if (!ctx) {
    throw new Error('useGameState must be used within a GameStateProvider');
  }
  return ctx;
}
