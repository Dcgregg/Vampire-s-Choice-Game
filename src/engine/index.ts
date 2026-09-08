/**
 * Story Engine — public API barrel.
 *
 * Layers:
 *   conditions  — determine availability of content/choices
 *   effects     — modify player state (the only mutation site)
 *   navigation  — determine the next scene / story progression
 *   engine      — orchestrator: selectChoice()
 *   validate    — content integrity checks
 */
export * from './types';
export * from './conditions';
export * from './effects';
export * from './navigation';
export * from './engine';
export * from './validate';
