import React from 'react';
import { useGameState } from '../../state/useGameState';
import { ScreenType } from '../../state/gameState';
import { BookOpen, User, Heart, Trophy, Settings } from 'lucide-react';

interface NavItem {
  id: ScreenType;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}

const NAV_ITEMS: NavItem[] = [
  { id: 'reading', label: 'Story', icon: BookOpen },
  { id: 'character', label: 'Character', icon: User },
  { id: 'relationships', label: 'Bonds', icon: Heart },
  { id: 'achievements', label: 'Trophies', icon: Trophy },
  { id: 'settings', label: 'Settings', icon: Settings },
];

export const BottomNav: React.FC = () => {
  const { activeScreen, setScreen, state } = useGameState();

  // Hide on landing screen or character creation for full cinematic immersion
  if (activeScreen === 'landing' || activeScreen === 'character_creation') {
    return null;
  }

  return (
    <nav className="fixed bottom-0 left-0 right-0 z-40 border-t border-[#2a1e35] bg-[#0c0912]/95 px-2 py-1 backdrop-blur-md pb-[max(0.5rem,env(safe-area-inset-bottom))]">
      <div className="mx-auto flex max-w-lg items-center justify-around">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const isActive = activeScreen === item.id;

          return (
            <button
              key={item.id}
              id={`nav-${item.id}-btn`}
              onClick={() => {
                if (item.id === 'reading' && !state.player) {
                  setScreen('character_creation');
                } else {
                  setScreen(item.id);
                }
              }}
              className={`relative flex min-h-[46px] min-w-[56px] flex-col items-center justify-center rounded-lg px-2 py-1 transition-all ${
                isActive
                  ? 'text-[#fae092]'
                  : 'text-stone-400 hover:text-stone-200 active:scale-95'
              }`}
            >
              {isActive && (
                <span className="absolute -top-1 h-1 w-6 rounded-full bg-gradient-to-r from-rose-600 via-[#e5c158] to-rose-600 shadow-[0_0_8px_rgba(229,193,88,0.6)]" />
              )}
              <Icon
                className={`h-5 w-5 transition-transform ${
                  isActive ? 'scale-110 text-[#fae092]' : 'text-stone-400'
                }`}
              />
              <span className="mt-1 font-interface text-[11px] font-medium tracking-tight">
                {item.label}
              </span>
            </button>
          );
        })}
      </div>
    </nav>
  );
};
