import React from 'react';
import { GameStateProvider, useGameState } from './state/useGameState';
import { Navbar } from './components/common/Navbar';
import { BottomNav } from './components/common/BottomNav';
import { AchievementBanner } from './components/common/AchievementBanner';
import { ConsequenceToast } from './components/common/ConsequenceToast';
import { OfflineIndicator } from './components/common/OfflineIndicator';
import { AccountBar } from './components/common/AccountBar';
import { TrustedProgressionStatus } from './components/common/TrustedProgressionStatus';

import { LandingScreen } from './components/screens/LandingScreen';
import { CharacterCreationScreen } from './components/screens/CharacterCreationScreen';
import { ReadingScreen } from './components/screens/ReadingScreen';
import { BookCompleteScreen } from './components/screens/BookCompleteScreen';
import { LibraryScreen } from './components/screens/LibraryScreen';
import { AdminScreen } from './components/screens/AdminScreen';
import { CharacterScreen } from './components/screens/CharacterScreen';
import { RelationshipsScreen } from './components/screens/RelationshipsScreen';
import { AchievementsScreen } from './components/screens/AchievementsScreen';
import { SettingsScreen } from './components/screens/SettingsScreen';
import { AboutScreen } from './components/screens/AboutScreen';
import { StagedReleasePreviewScreen } from './components/screens/StagedReleasePreviewScreen';
import { BetaReleasePlayerScreen } from './components/screens/BetaReleasePlayerScreen';

const MainContent: React.FC = () => {
  const { activeScreen } = useGameState();

  return (
    <div className="min-h-screen bg-[#09070c] text-[#ede5d8] flex flex-col font-sans selection:bg-rose-950 selection:text-rose-200">
      <Navbar />
      <AccountBar />
      <OfflineIndicator />
      <TrustedProgressionStatus />
      <AchievementBanner />
      <ConsequenceToast />

      <main className="flex-1 w-full relative">
        {activeScreen === 'landing' && <LandingScreen />}
        {activeScreen === 'character_creation' && <CharacterCreationScreen />}
        {activeScreen === 'reading' && <ReadingScreen />}
        {activeScreen === 'book_complete' && <BookCompleteScreen />}
        {activeScreen === 'library' && <LibraryScreen />}
        {activeScreen === 'admin' && <AdminScreen />}
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
  const params = new URLSearchParams(window.location.search);
  const stagedBook = params.get('stagedBook');
  const betaBook = params.get('betaBook');
  // Preview and beta must never initialise the normal game state or its cloud sync.
  if (stagedBook && /^book[1-9][0-9]*$/.test(stagedBook)) return <div className="min-h-screen bg-[#09070c] text-[#ede5d8] font-sans"><StagedReleasePreviewScreen bookId={stagedBook} /></div>;
  if (betaBook && /^book[1-9][0-9]*$/.test(betaBook)) return <div className="min-h-screen bg-[#09070c] text-[#ede5d8] font-sans"><BetaReleasePlayerScreen bookId={betaBook} /></div>;
  return (
    <GameStateProvider>
      <MainContent />
    </GameStateProvider>
  );
}
