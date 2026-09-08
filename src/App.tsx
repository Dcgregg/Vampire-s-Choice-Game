import React from 'react';
import { GameStateProvider, useGameState } from './state/useGameState';
import { Navbar } from './components/common/Navbar';
import { BottomNav } from './components/common/BottomNav';
import { AchievementBanner } from './components/common/AchievementBanner';
import { ConsequenceToast } from './components/common/ConsequenceToast';
import { OfflineIndicator } from './components/common/OfflineIndicator';

import { LandingScreen } from './components/screens/LandingScreen';
import { CharacterCreationScreen } from './components/screens/CharacterCreationScreen';
import { ReadingScreen } from './components/screens/ReadingScreen';
import { CharacterScreen } from './components/screens/CharacterScreen';
import { RelationshipsScreen } from './components/screens/RelationshipsScreen';
import { AchievementsScreen } from './components/screens/AchievementsScreen';
import { SettingsScreen } from './components/screens/SettingsScreen';
import { AboutScreen } from './components/screens/AboutScreen';

const MainContent: React.FC = () => {
  const { activeScreen } = useGameState();

  return (
    <div className="min-h-screen bg-[#09070c] text-[#ede5d8] flex flex-col font-sans selection:bg-rose-950 selection:text-rose-200">
      <Navbar />
      <OfflineIndicator />
      <AchievementBanner />
      <ConsequenceToast />

      <main className="flex-1 w-full relative">
        {activeScreen === 'landing' && <LandingScreen />}
        {activeScreen === 'character_creation' && <CharacterCreationScreen />}
        {activeScreen === 'reading' && <ReadingScreen />}
        {activeScreen === 'character' && <CharacterScreen />}
        {activeScreen === 'relationships' && <RelationshipsScreen />}
        {activeScreen === 'achievements' && <AchievementsScreen />}
        {activeScreen === 'settings' && <SettingsScreen />}
        {activeScreen === 'about' && <AboutScreen />}
      </main>

      <BottomNav />
    </div>
  );
};

export default function App() {
  return (
    <GameStateProvider>
      <MainContent />
    </GameStateProvider>
  );
}
