import React, { useRef, useEffect } from 'react';
import { useGameState } from '../../state/useGameState';
import { getSceneById } from '../../data/story';
import { isChoiceAvailable, isParagraphVisible } from '../../engine';
import { SceneChoice } from '../../types';
import { Heart, AlertTriangle, Sparkles, ChevronRight, Bookmark, Type, Lock } from 'lucide-react';

export const ReadingScreen: React.FC = () => {
  const { state, makeChoice, interpolate, updateSettings } = useGameState();
  const contentRef = useRef<HTMLDivElement>(null);

  const currentSceneId = state.progress.currentSceneId || 'b1_c1_s1';
  const scene = getSceneById(currentSceneId);

  // Scroll to top when scene changes
  useEffect(() => {
    if (contentRef.current) {
      contentRef.current.scrollTo({ top: 0, behavior: 'smooth' });
    }
  }, [currentSceneId]);

  if (!scene) {
    return (
      <div className="flex min-h-[70vh] flex-col items-center justify-center p-6 text-center">
        <h3 className="font-display text-xl text-rose-300">The shadows have closed</h3>
        <p className="mt-2 text-sm text-stone-400">
          Scene archive "{currentSceneId}" could not be resolved.
        </p>
        <button
          onClick={() => makeChoice({ id: 'fallback', text: 'Return to start', nextSceneId: 'b1_c1_s1' })}
          className="mt-4 rounded-xl border border-[#c5a059] bg-rose-950 px-4 py-2 text-xs text-white"
        >
          Return to Blackthorn Gates
        </button>
      </div>
    );
  }

  // Determine font size class from settings
  const getFontSizeClasses = () => {
    switch (state.settings.fontSize) {
      case 'large':
        return {
          body: 'text-lg sm:text-xl leading-relaxed sm:leading-loose',
          dialogue: 'text-base sm:text-lg',
          choice: 'text-sm sm:text-base',
        };
      case 'xlarge':
        return {
          body: 'text-xl sm:text-2xl leading-loose',
          dialogue: 'text-lg sm:text-xl',
          choice: 'text-base sm:text-lg',
        };
      case 'normal':
      default:
        return {
          body: 'text-base sm:text-lg leading-relaxed sm:leading-relaxed',
          dialogue: 'text-sm sm:text-base',
          choice: 'text-xs sm:text-sm',
        };
    }
  };

  const fontClasses = getFontSizeClasses();

  // Cycle font size
  const cycleFontSize = () => {
    const nextSize =
      state.settings.fontSize === 'normal'
        ? 'large'
        : state.settings.fontSize === 'large'
        ? 'xlarge'
        : 'normal';
    updateSettings({ fontSize: nextSize });
  };

  return (
    <div
      ref={contentRef}
      className="relative min-h-[calc(100vh-3.5rem)] pb-24 pt-4 px-4 sm:px-6 overflow-y-auto"
    >
      {/* Novel Reading Column constraint: max-w-2xl (~672px) for optimal typographic line-length */}
      <article className="mx-auto max-w-2xl">
        {/* Book & Chapter Header */}
        <header className="mb-8 text-center border-b border-[#2d1e38]/80 pb-6 pt-2">
          <div className="flex items-center justify-between text-xs text-stone-400 mb-3 px-1">
            <div className="flex items-center gap-1.5">
              <Bookmark className="w-3.5 h-3.5 text-[#c5a059]" />
              <span className="font-interface uppercase tracking-widest text-[11px] text-[#c5a059]">
                Book I: Bloodlines of Blackthorn
              </span>
            </div>

            {/* Accessibility Font Size Toggle */}
            <button
              id="reading-font-toggle-btn"
              onClick={cycleFontSize}
              className="flex items-center gap-1 rounded-full border border-white/10 bg-black/40 px-2.5 py-1 text-[11px] text-stone-300 hover:border-[#c5a059]/60 hover:text-white transition"
              title="Adjust Reading Text Size"
            >
              <Type className="w-3 h-3 text-[#e5c158]" />
              <span className="capitalize">{state.settings.fontSize}</span>
            </button>
          </div>

          <span className="font-interface text-xs font-semibold uppercase tracking-widest text-rose-400">
            Chapter {scene.chapterNumber}
          </span>
          <h1 className="font-display text-2xl sm:text-3xl font-bold text-[#f5f0e6] mt-1 tracking-wide">
            {scene.chapterTitle}
          </h1>
          <h2 className="font-narrative italic text-sm text-[#d6cbbe] mt-1">
            — {scene.sceneTitle} —
          </h2>
        </header>

        {/* Narrative Paragraphs */}
        <div className="space-y-5 text-[#ede5d8] font-narrative">
          {scene.paragraphs.map((para, idx) => (
            <p
              key={idx}
              className={`${fontClasses.body} text-justify [text-align-last:left] tracking-normal`}
            >
              {idx === 0 && (
                <span className="float-left mr-2.5 font-display text-4xl sm:text-5xl font-bold leading-none text-[#fae092] filter drop-shadow-[0_2px_4px_rgba(0,0,0,0.8)]">
                  {interpolate(para).charAt(0)}
                </span>
              )}
              {idx === 0 ? interpolate(para).slice(1) : interpolate(para)}
            </p>
          ))}
        </div>

        {/* Dynamic Condition Paragraphs (reacting to prior choices) */}
        {scene.conditionParagraphs?.map((cond, idx) => {
          if (!isParagraphVisible(cond, state)) return null;

          return (
            <div
              key={`cond-${idx}`}
              className="my-5 rounded-xl border-l-2 border-[#c5a059] bg-[#1a1122]/60 p-4 font-narrative text-[#ede5d8] shadow-sm animate-in fade-in duration-300"
            >
              <div className="mb-1 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-[#e5c158]">
                <Sparkles className="w-3 h-3" />
                <span>Narrative Resonance</span>
              </div>
              {cond.paragraphs.map((p, pIdx) => (
                <p key={pIdx} className={`${fontClasses.body} italic mt-1 text-[#f5f0e6]`}>
                  {interpolate(p)}
                </p>
              ))}
            </div>
          );
        })}

        {/* Dialogues (if present) */}
        {scene.dialogues && scene.dialogues.length > 0 && (
          <div className="my-6 space-y-4">
            {scene.dialogues.map((dlg, idx) => {
              const char = dlg.characterId ? state.relationships[dlg.characterId] : null;

              return (
                <div
                  key={idx}
                  className="relative rounded-xl border border-[#2d1e38] bg-gradient-to-r from-[#170e20] to-[#120a1a] p-4 shadow-sm"
                >
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <div className="flex h-6 w-6 items-center justify-center rounded-full border border-[#c5a059]/40 bg-rose-950/50 text-xs">
                        {dlg.characterId === 'lucian' ? '🦇' : dlg.characterId === 'isolde' ? '🧪' : dlg.characterId === 'nico' ? '📜' : '🕯️'}
                      </div>
                      <span className="font-display text-xs font-bold uppercase tracking-wider text-[#fae092]">
                        {dlg.speaker}
                      </span>
                    </div>

                    {/* Subtle affinity indicator */}
                    {char && (
                      <div
                        className="flex items-center gap-1 text-[11px] text-rose-300"
                        title={`${char.name} Affinity: ${char.affinity}/100`}
                      >
                        <Heart className="w-3 h-3 fill-rose-600 text-rose-500" />
                        <span className="font-interface font-medium">{char.affinity}</span>
                      </div>
                    )}
                  </div>

                  <p
                    className={`font-narrative italic text-[#f7f2ea] ${fontClasses.dialogue} leading-relaxed pl-2 border-l border-rose-900/50`}
                  >
                    "{interpolate(dlg.text)}"
                  </p>
                </div>
              );
            })}
          </div>
        )}

        {/* Choice Section */}
        <section className="mt-10 pt-6 border-t border-[#2a1b36]">
          <div className="mb-4 flex items-center justify-center gap-2 text-center">
            <span className="h-[1px] w-8 bg-[#c5a059]/50" />
            <span className="font-interface text-xs font-bold uppercase tracking-widest text-[#fae092]">
              Your Choice
            </span>
            <span className="h-[1px] w-8 bg-[#c5a059]/50" />
          </div>

          <div className="space-y-3">
            {scene.choices.map((choice: SceneChoice) => {
              const isRomantic = choice.isRomantic;
              const isDangerous = choice.isDangerous;
              const available = isChoiceAvailable(choice, state);

              return (
                <button
                  key={choice.id}
                  id={`choice-${choice.id}`}
                  data-testid={`choice-${choice.id}`}
                  disabled={!available}
                  aria-disabled={!available}
                  onClick={() => {
                    if (available) makeChoice(choice);
                  }}
                  className={`group relative w-full rounded-xl border p-4 text-left transition-all duration-300 ${
                    !available
                      ? 'cursor-not-allowed border-white/10 bg-black/40 opacity-50'
                      : 'hover:scale-[1.01] active:scale-[0.99] '
                  }${
                    available && isRomantic
                      ? 'border-rose-800/60 bg-gradient-to-r from-[#200e1f] to-[#140816] hover:border-rose-600 shadow-[0_2px_12px_rgba(190,18,60,0.15)]'
                      : available && isDangerous
                      ? 'border-amber-700/60 bg-gradient-to-r from-[#22130e] to-[#140a08] hover:border-amber-500 shadow-[0_2px_12px_rgba(180,83,9,0.15)]'
                      : available
                      ? 'border-[#332244]/80 bg-gradient-to-r from-[#170e22] to-[#100918] hover:border-[#c5a059]/60 hover:bg-[#1f132e]'
                      : ''
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1">
                      {/* Emotional Badges */}
                      <div className="flex items-center gap-2 mb-1.5">
                        {!available && (
                          <span
                            data-testid={`choice-locked-${choice.id}`}
                            className="inline-flex items-center gap-1 rounded-full bg-black/60 border border-white/15 px-2 py-0.5 text-[10px] font-semibold text-stone-300"
                          >
                            <Lock className="w-2.5 h-2.5 text-stone-400" />
                            <span>Locked</span>
                          </span>
                        )}
                        {available && isRomantic && (
                          <span className="inline-flex items-center gap-1 rounded-full bg-rose-950/80 border border-rose-800/60 px-2 py-0.5 text-[10px] font-semibold text-rose-200">
                            <Heart className="w-2.5 h-2.5 fill-rose-500 text-rose-500" />
                            <span>Romantic Arc</span>
                          </span>
                        )}
                        {available && isDangerous && (
                          <span className="inline-flex items-center gap-1 rounded-full bg-amber-950/80 border border-amber-800/60 px-2 py-0.5 text-[10px] font-semibold text-amber-200">
                            <AlertTriangle className="w-2.5 h-2.5 text-amber-400" />
                            <span>High Stakes</span>
                          </span>
                        )}
                      </div>

                      {/* Choice Main Text */}
                      <p
                        className={`font-narrative font-semibold text-[#f5f0e6] group-hover:text-[#fae092] transition-colors ${fontClasses.choice}`}
                      >
                        {interpolate(choice.text)}
                      </p>

                      {/* Consequence / Flavor Hint */}
                      {choice.consequencesSummary && (
                        <p className="mt-1 font-interface text-[11px] text-stone-400">
                          {choice.consequencesSummary}
                        </p>
                      )}
                    </div>

                    <div className="mt-1 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-white/10 bg-black/40 text-stone-400 transition-all group-hover:border-[#c5a059] group-hover:text-[#fae092] group-hover:translate-x-0.5">
                      <ChevronRight className="h-3.5 w-3.5" />
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        </section>
      </article>
    </div>
  );
};
