import React, { useState } from 'react';
import { useGameState } from '../../state/useGameState';
import { Type, Volume2, VolumeX, RotateCcw, AlertTriangle, Check, Info, Sparkles } from 'lucide-react';
import { PWAInstallButton } from '../common/PWAInstallButton';

export const SettingsScreen: React.FC = () => {
  const { state, updateSettings, resetAllData, setScreen } = useGameState();
  const [showResetConfirm, setShowResetConfirm] = useState(false);
  const [resetSuccess, setResetSuccess] = useState(false);

  const handleConfirmReset = () => {
    resetAllData();
    setShowResetConfirm(false);
    setResetSuccess(true);
    setTimeout(() => {
      setResetSuccess(false);
      setScreen('landing');
    }, 1200);
  };

  return (
    <div className="mx-auto max-w-lg px-4 py-6 pb-24 space-y-6">
      {/* Header */}
      <div className="text-center">
        <span className="text-[10px] uppercase tracking-widest text-[#e5c158] font-semibold">
          Preferences & Engine
        </span>
        <h2 className="font-display text-2xl font-bold text-[#f5f0e6] mt-1">
          Manuscript Settings
        </h2>
        <p className="font-narrative italic text-xs text-[#d6cbbe] mt-1">
          Customize reading comfort, ambience, and local prototype state.
        </p>
      </div>

      {/* Typography & Readability */}
      <div className="rounded-2xl border border-white/10 bg-[#140e1c] p-4 sm:p-5 space-y-4">
        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-[#fae092]">
          <Type className="w-4 h-4" />
          <span>Reading Typography</span>
        </div>

        <div>
          <label className="text-xs text-stone-300 block mb-2">Narrative Font Size</label>
          <div className="grid grid-cols-3 gap-2">
            {(['normal', 'large', 'xlarge'] as const).map((size) => (
              <button
                key={size}
                id={`font-size-${size}`}
                onClick={() => updateSettings({ fontSize: size })}
                className={`rounded-xl border py-2.5 px-3 text-xs capitalize transition font-medium ${
                  state.settings.fontSize === size
                    ? 'border-[#c5a059] bg-[#291738] text-[#fae092] shadow-sm'
                    : 'border-white/10 bg-black/40 text-stone-400 hover:border-white/20 hover:text-white'
                }`}
              >
                {size}
              </button>
            ))}
          </div>
          <p className="text-[11px] text-stone-400 mt-2">
            Optimized for single-hand mobile reading and comfortable line-lengths on desktop.
          </p>
        </div>
      </div>

      {/* Soundscape & Ambience */}
      <div className="rounded-2xl border border-white/10 bg-[#140e1c] p-4 sm:p-5 space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-[#fae092]">
            {state.settings.ambientAudio ? (
              <Volume2 className="w-4 h-4 text-[#e5c158]" />
            ) : (
              <VolumeX className="w-4 h-4 text-stone-400" />
            )}
            <span>Gothic Soundscape</span>
          </div>
          <button
            id="settings-audio-toggle"
            onClick={() => updateSettings({ ambientAudio: !state.settings.ambientAudio })}
            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
              state.settings.ambientAudio ? 'bg-rose-900' : 'bg-stone-800'
            }`}
          >
            <span
              className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                state.settings.ambientAudio ? 'translate-x-6' : 'translate-x-1'
              }`}
            />
          </button>
        </div>
        <p className="text-xs text-stone-400 leading-relaxed">
          Generates procedural harmonic low-frequency organ drone and candle breeze via the browser's Web Audio API. Zero external downloads; works offline.
        </p>
      </div>

      {/* Progressive Web App */}
      <div className="rounded-2xl border border-white/10 bg-[#140e1c] p-4 sm:p-5 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-[#fae092]">
            <Sparkles className="w-4 h-4" />
            <span>Installable Web App</span>
          </div>
          <PWAInstallButton />
        </div>
        <p className="text-xs text-stone-400 leading-relaxed">
          Install Vampire's Choice on your phone home screen or desktop for a standalone, distraction-free reading experience with local offline caching.
        </p>
      </div>

      {/* Local Save & Reset */}
      <div className="rounded-2xl border border-rose-950/50 bg-[#140b17] p-4 sm:p-5 space-y-3">
        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-rose-300">
          <RotateCcw className="w-4 h-4" />
          <span>Local Data Management</span>
        </div>
        <p className="text-xs text-stone-400 leading-relaxed">
          All prototype state (protagonist, story flags, affinities, achievements, and currency) is stored securely in your browser’s local storage.
        </p>

        {resetSuccess ? (
          <div className="flex items-center gap-2 rounded-xl bg-emerald-950/50 border border-emerald-800 p-3 text-xs text-emerald-200">
            <Check className="w-4 h-4" />
            <span>Local data successfully reset. Returning to entrance...</span>
          </div>
        ) : (
          <button
            id="reset-all-data-btn"
            onClick={() => setShowResetConfirm(true)}
            className="flex items-center gap-2 rounded-xl border border-rose-900/60 bg-rose-950/40 px-4 py-2.5 text-xs font-semibold text-rose-300 hover:bg-rose-900/50 hover:text-white transition"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            <span>Reset Local Story & Character</span>
          </button>
        )}
      </div>

      {/* Reset Confirmation Modal */}
      {showResetConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 backdrop-blur-sm">
          <div className="w-full max-w-sm rounded-2xl border border-rose-800/60 bg-[#140b17] p-6 shadow-2xl text-[#ede5d8]">
            <div className="flex items-center gap-2.5 text-rose-400 mb-3">
              <AlertTriangle className="w-5 h-5" />
              <h3 className="font-display text-base font-bold text-white">
                Reset All Story Data?
              </h3>
            </div>
            <p className="text-xs text-stone-300 leading-relaxed">
              This will erase your protagonist, story flags, relationship progress, and trophies, returning Vampire's Choice to a fresh state.
            </p>
            <div className="mt-5 flex gap-3">
              <button
                onClick={() => setShowResetConfirm(false)}
                className="flex-1 rounded-xl border border-white/10 bg-black/40 py-2.5 text-xs font-semibold text-stone-300 hover:text-white"
              >
                Cancel
              </button>
              <button
                id="confirm-modal-reset-btn"
                onClick={handleConfirmReset}
                className="flex-1 rounded-xl bg-rose-900 py-2.5 text-xs font-semibold text-white shadow hover:bg-rose-800"
              >
                Confirm Reset
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Architecture Info */}
      <div className="rounded-xl border border-white/5 bg-black/40 p-4 text-center text-xs text-stone-500 space-y-1">
        <p className="font-interface font-medium text-stone-400">Vampire's Choice Prototype v1.0.0</p>
        <p>Gothic Narrative Engine • Modular React + TypeScript Architecture</p>
      </div>
    </div>
  );
};
