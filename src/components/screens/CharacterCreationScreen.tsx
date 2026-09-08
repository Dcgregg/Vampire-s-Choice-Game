import React, { useState } from 'react';
import { useGameState } from '../../state/useGameState';
import { GenderIdentity, SexualOrientation } from '../../types';
import { Sparkles, ArrowRight, ArrowLeft, Check, Compass, ShieldAlert } from 'lucide-react';

const SUGGESTED_NAMES = ['Elena', 'Alex', 'Rowan', 'Julian', 'Clara', 'Damian', 'Seraphina', 'Valen'];

const GENDER_OPTIONS: { value: GenderIdentity; label: string; desc: string }[] = [
  { value: 'Woman', label: 'Woman', desc: 'She / Her' },
  { value: 'Man', label: 'Man', desc: 'He / Him' },
  { value: 'Non-binary', label: 'Non-binary', desc: 'They / Them' },
  { value: 'Other', label: 'Other', desc: 'Self-determined' },
  { value: 'Prefer not to say', label: 'Prefer not to say', desc: 'Unspecified' },
];

const ORIENTATION_OPTIONS: { value: SexualOrientation; label: string; desc: string }[] = [
  { value: 'Bisexual', label: 'Bisexual', desc: 'Drawn to multiple genders' },
  { value: 'Pansexual', label: 'Pansexual', desc: 'Attraction without gender boundaries' },
  { value: 'Straight', label: 'Straight', desc: 'Attracted to complementary gender' },
  { value: 'Gay', label: 'Gay', desc: 'Attracted to men' },
  { value: 'Lesbian', label: 'Lesbian', desc: 'Attracted to women' },
  { value: 'Asexual', label: 'Asexual', desc: 'Focus on emotional & intellectual bonds' },
  { value: 'Other', label: 'Other', desc: 'Fluid or self-defined' },
  { value: 'Prefer not to say', label: 'Prefer not to say', desc: 'Private inclination' },
];

export const CharacterCreationScreen: React.FC = () => {
  const { createCharacter, setScreen, state } = useGameState();

  const [step, setStep] = useState<1 | 2 | 3 | 4>(1);
  const [name, setName] = useState<string>(state.player?.name || 'Elena');
  const [gender, setGender] = useState<GenderIdentity>(state.player?.genderIdentity || 'Woman');
  const [orientation, setOrientation] = useState<SexualOrientation>(
    state.player?.sexualOrientation || 'Bisexual'
  );
  const [errorMsg, setErrorMsg] = useState<string>('');

  const handleNextFromStep1 = () => {
    if (!name.trim()) {
      setErrorMsg('Please enter a name for your protagonist.');
      return;
    }
    setErrorMsg('');
    setStep(2);
  };

  const handleConfirmCreation = () => {
    createCharacter(name, gender, orientation);
  };

  return (
    <div className="relative min-h-[calc(100vh-3.5rem)] flex flex-col justify-between items-center px-4 py-6 sm:py-10 max-w-lg mx-auto">
      {/* Background vignette & ambient candle glow */}
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_center,_var(--tw-gradient-stops))] from-[#1d1024]/40 via-[#0a070e] to-[#040306]" />

      {/* Header with Step Indicator */}
      <div className="relative z-10 w-full mb-6">
        <div className="flex items-center justify-between mb-3">
          <button
            onClick={() => {
              if (step > 1) {
                setStep((s) => (s - 1) as 1 | 2 | 3 | 4);
              } else {
                setScreen('landing');
              }
            }}
            className="flex items-center gap-1.5 text-xs text-stone-400 hover:text-white transition"
          >
            <ArrowLeft className="w-4 h-4" />
            <span>{step === 1 ? 'Cancel' : 'Back'}</span>
          </button>
          <span className="font-interface text-xs font-semibold uppercase tracking-widest text-[#c5a059]">
            Step {step} of 4
          </span>
        </div>

        {/* Step Progress Bar */}
        <div className="h-1 w-full rounded-full bg-white/10 overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-rose-700 via-[#c5a059] to-rose-700 transition-all duration-300"
            style={{ width: `${(step / 4) * 100}%` }}
          />
        </div>
      </div>

      {/* Step Content Container */}
      <div className="relative z-10 my-auto w-full">
        {/* STEP 1: NAME */}
        {step === 1 && (
          <div className="animate-in fade-in slide-in-from-right-4 duration-300">
            <div className="text-center mb-6">
              <span className="text-xs uppercase tracking-widest text-[#e5c158] font-semibold">
                Identity & Heritage
              </span>
              <h2 className="font-display text-2xl sm:text-3xl font-bold text-[#f5f0e6] mt-1">
                Name Your Protagonist
              </h2>
              <p className="font-narrative italic text-sm text-[#d6cbbe] mt-2 max-w-sm mx-auto">
                What name is penned upon the wax-sealed invitation to Blackthorn Academy?
              </p>
            </div>

            <div className="space-y-4">
              <div className="relative">
                <input
                  id="protagonist-name-input"
                  type="text"
                  maxLength={28}
                  value={name}
                  onChange={(e) => {
                    setName(e.target.value);
                    if (errorMsg) setErrorMsg('');
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') handleNextFromStep1();
                  }}
                  placeholder="e.g., Elena, Alex, Rowan..."
                  className="w-full rounded-xl border border-[#c5a059]/50 bg-[#140c1c] px-4 py-3.5 text-center font-display text-lg text-[#f5f0e6] placeholder-stone-600 shadow-inner focus:border-[#fae092] focus:outline-none focus:ring-1 focus:ring-[#fae092]"
                  autoFocus
                />
              </div>

              {errorMsg && (
                <div className="flex items-center gap-1.5 justify-center text-xs text-rose-400">
                  <ShieldAlert className="w-3.5 h-3.5" />
                  <span>{errorMsg}</span>
                </div>
              )}

              {/* Suggestions */}
              <div>
                <p className="text-[11px] uppercase tracking-wider text-stone-500 mb-2 text-center">
                  Suggested Archetype Names
                </p>
                <div className="flex flex-wrap justify-center gap-2">
                  {SUGGESTED_NAMES.map((sug) => (
                    <button
                      key={sug}
                      type="button"
                      onClick={() => {
                        setName(sug);
                        if (errorMsg) setErrorMsg('');
                      }}
                      className={`rounded-full border px-3 py-1 text-xs transition ${
                        name === sug
                          ? 'border-[#c5a059] bg-[#291736] text-[#fae092]'
                          : 'border-white/10 bg-black/40 text-stone-300 hover:border-[#c5a059]/40 hover:text-white'
                      }`}
                    >
                      {sug}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <button
              id="name-next-btn"
              onClick={handleNextFromStep1}
              className="mt-8 w-full flex items-center justify-center gap-2 rounded-xl border border-[#c5a059] bg-gradient-to-r from-rose-950 via-rose-900 to-rose-950 py-3.5 font-display text-xs font-bold uppercase tracking-widest text-white shadow-lg transition hover:from-rose-900 hover:to-rose-800 active:scale-[0.98]"
            >
              <span>Continue</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        )}

        {/* STEP 2: GENDER IDENTITY */}
        {step === 2 && (
          <div className="animate-in fade-in slide-in-from-right-4 duration-300">
            <div className="text-center mb-6">
              <span className="text-xs uppercase tracking-widest text-[#e5c158] font-semibold">
                Form & Presence
              </span>
              <h2 className="font-display text-2xl sm:text-3xl font-bold text-[#f5f0e6] mt-1">
                Gender Identity
              </h2>
              <p className="font-narrative italic text-sm text-[#d6cbbe] mt-2 max-w-sm mx-auto">
                How does your protagonist walk through the mortal world and the nightborn courts?
              </p>
            </div>

            <div className="space-y-2.5">
              {GENDER_OPTIONS.map((opt) => {
                const isSelected = gender === opt.value;
                return (
                  <button
                    key={opt.value}
                    id={`gender-${opt.value.toLowerCase().replace(/\s+/g, '-')}`}
                    onClick={() => setGender(opt.value)}
                    className={`w-full flex items-center justify-between rounded-xl border p-3.5 text-left transition-all ${
                      isSelected
                        ? 'border-[#c5a059] bg-[#22132e] shadow-[0_0_15px_rgba(197,160,89,0.2)]'
                        : 'border-white/10 bg-[#120a1a]/70 hover:border-white/20 hover:bg-[#180f22]'
                    }`}
                  >
                    <div>
                      <div className="font-display text-sm font-semibold text-[#f5f0e6]">
                        {opt.label}
                      </div>
                      <div className="text-xs text-stone-400 mt-0.5">{opt.desc}</div>
                    </div>
                    {isSelected && (
                      <div className="flex h-6 w-6 items-center justify-center rounded-full bg-[#c5a059] text-black">
                        <Check className="h-3.5 w-3.5 stroke-[3]" />
                      </div>
                    )}
                  </button>
                );
              })}
            </div>

            <button
              id="gender-next-btn"
              onClick={() => setStep(3)}
              className="mt-8 w-full flex items-center justify-center gap-2 rounded-xl border border-[#c5a059] bg-gradient-to-r from-rose-950 via-rose-900 to-rose-950 py-3.5 font-display text-xs font-bold uppercase tracking-widest text-white shadow-lg transition hover:from-rose-900 hover:to-rose-800 active:scale-[0.98]"
            >
              <span>Continue to Romantic Inclination</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        )}

        {/* STEP 3: SEXUAL ORIENTATION */}
        {step === 3 && (
          <div className="animate-in fade-in slide-in-from-right-4 duration-300">
            <div className="text-center mb-6">
              <span className="text-xs uppercase tracking-widest text-[#e5c158] font-semibold">
                Desire & Affection
              </span>
              <h2 className="font-display text-2xl sm:text-3xl font-bold text-[#f5f0e6] mt-1">
                Romantic Inclination
              </h2>
              <p className="font-narrative italic text-sm text-[#d6cbbe] mt-2 max-w-sm mx-auto">
                Toward whom might your heart or passions lean when darkness falls?
              </p>
            </div>

            <div className="space-y-2 max-h-[50vh] overflow-y-auto pr-1">
              {ORIENTATION_OPTIONS.map((opt) => {
                const isSelected = orientation === opt.value;
                return (
                  <button
                    key={opt.value}
                    id={`orient-${opt.value.toLowerCase().replace(/\s+/g, '-')}`}
                    onClick={() => setOrientation(opt.value)}
                    className={`w-full flex items-center justify-between rounded-xl border p-3 text-left transition-all ${
                      isSelected
                        ? 'border-[#c5a059] bg-[#22132e] shadow-[0_0_15px_rgba(197,160,89,0.2)]'
                        : 'border-white/10 bg-[#120a1a]/70 hover:border-white/20 hover:bg-[#180f22]'
                    }`}
                  >
                    <div>
                      <div className="font-display text-sm font-semibold text-[#f5f0e6]">
                        {opt.label}
                      </div>
                      <div className="text-xs text-stone-400 mt-0.5">{opt.desc}</div>
                    </div>
                    {isSelected && (
                      <div className="flex h-6 w-6 items-center justify-center rounded-full bg-[#c5a059] text-black">
                        <Check className="h-3.5 w-3.5 stroke-[3]" />
                      </div>
                    )}
                  </button>
                );
              })}
            </div>

            <button
              id="orientation-next-btn"
              onClick={() => setStep(4)}
              className="mt-6 w-full flex items-center justify-center gap-2 rounded-xl border border-[#c5a059] bg-gradient-to-r from-rose-950 via-rose-900 to-rose-950 py-3.5 font-display text-xs font-bold uppercase tracking-widest text-white shadow-lg transition hover:from-rose-900 hover:to-rose-800 active:scale-[0.98]"
            >
              <span>Review & Awaken</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        )}

        {/* STEP 4: DRAMATIC CONFIRMATION */}
        {step === 4 && (
          <div className="animate-in fade-in zoom-in-95 duration-500 text-center">
            {/* Ornate Frame Card */}
            <div className="relative rounded-2xl border border-[#c5a059]/60 bg-gradient-to-b from-[#1a0f24] to-[#0d0714] p-6 sm:p-8 shadow-[0_0_40px_rgba(190,18,60,0.3)]">
              {/* Corner Filigree Pins */}
              <div className="absolute top-2 left-2 h-3 w-3 border-t border-l border-[#c5a059]" />
              <div className="absolute top-2 right-2 h-3 w-3 border-t border-r border-[#c5a059]" />
              <div className="absolute bottom-2 left-2 h-3 w-3 border-b border-l border-[#c5a059]" />
              <div className="absolute bottom-2 right-2 h-3 w-3 border-b border-r border-[#c5a059]" />

              <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full border border-[#c5a059]/50 bg-rose-950/40 text-2xl shadow-inner">
                🕯️
              </div>

              <span className="text-[11px] uppercase tracking-widest text-[#e5c158] font-semibold">
                The Rite of Awakening
              </span>

              <h2 className="font-display text-2xl sm:text-3xl font-extrabold text-[#f5f0e6] mt-2">
                Your story begins, <span className="text-[#fae092]">{name}</span>.
              </h2>

              <p className="font-narrative italic text-base text-[#d8cfc4] mt-3 leading-relaxed">
                "The gates of Blackthorn Academy open only when the fog rolls in from the abyss. Beyond this threshold, immortals whisper your name, and every choice will demand its price."
              </p>

              {/* Dossier Summary */}
              <div className="mt-6 rounded-xl border border-white/10 bg-black/40 p-4 text-left text-xs space-y-2 text-[#d6cbbe]">
                <div className="flex justify-between border-b border-white/5 pb-1.5">
                  <span className="text-stone-400">Protagonist Name</span>
                  <span className="font-semibold text-white">{name}</span>
                </div>
                <div className="flex justify-between border-b border-white/5 pb-1.5">
                  <span className="text-stone-400">Gender Identity</span>
                  <span className="text-white">{gender}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-stone-400">Romantic Inclination</span>
                  <span className="text-white">{orientation}</span>
                </div>
              </div>

              {/* Awaken Button */}
              <button
                id="character-confirm-awaken-btn"
                onClick={handleConfirmCreation}
                className="mt-6 w-full flex items-center justify-center gap-2.5 rounded-xl border border-[#c5a059] bg-gradient-to-r from-rose-900 via-rose-800 to-rose-900 py-4 font-display text-sm font-bold uppercase tracking-widest text-[#f5f0e6] shadow-[0_4px_25px_rgba(190,18,60,0.5)] transition hover:scale-[1.02] hover:shadow-[0_4px_30px_rgba(190,18,60,0.7)] active:scale-[0.98]"
              >
                <Sparkles className="w-4 h-4 text-[#fae092]" />
                <span>Awaken in Blackthorn</span>
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Footer Navigation Back to Landing */}
      <div className="relative z-10 mt-6 text-center text-xs text-stone-500">
        <span>Vampire's Choice Character Protocol</span>
      </div>
    </div>
  );
};
