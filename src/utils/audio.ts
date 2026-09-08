/**
 * Procedural Gothic Ambient Soundscape via Web Audio API
 * Generates soft, atmospheric cello/organ harmonic drones & candlelit winds.
 * Completely offline and lightweight (zero external assets).
 */

class GothicSoundEngine {
  private ctx: AudioContext | null = null;
  private masterGain: GainNode | null = null;
  private oscillators: OscillatorNode[] = [];
  private isRunning: boolean = false;

  public init() {
    if (this.ctx) return;
    const AudioCtx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    if (!AudioCtx) return;
    this.ctx = new AudioCtx();
    this.masterGain = this.ctx.createGain();
    this.masterGain.gain.setValueAtTime(0.0001, this.ctx.currentTime);
    this.masterGain.connect(this.ctx.destination);
  }

  public playAtmosphere() {
    try {
      this.init();
      if (!this.ctx || !this.masterGain) return;

      if (this.ctx.state === 'suspended') {
        this.ctx.resume();
      }

      if (this.isRunning) return;
      this.isRunning = true;

      // Chord frequencies: A minor 9 (A1, E2, A2, C3, G3) for ancient gothic mystery
      const freqs = [55.0, 82.41, 110.0, 130.81, 196.0];

      freqs.forEach((freq, idx) => {
        if (!this.ctx || !this.masterGain) return;
        const osc = this.ctx.createOscillator();
        const gain = this.ctx.createGain();
        const filter = this.ctx.createBiquadFilter();

        osc.type = idx % 2 === 0 ? 'sine' : 'triangle';
        osc.frequency.setValueAtTime(freq, this.ctx.currentTime);

        // Low-pass filter for warmth and candlelit darkness
        filter.type = 'lowpass';
        filter.frequency.setValueAtTime(280 + idx * 40, this.ctx.currentTime);

        // Gentle undulating LFO for breathing movement
        const lfo = this.ctx.createOscillator();
        const lfoGain = this.ctx.createGain();
        lfo.frequency.setValueAtTime(0.08 + idx * 0.02, this.ctx.currentTime);
        lfoGain.gain.setValueAtTime(0.02, this.ctx.currentTime);
        lfo.connect(lfoGain);

        gain.gain.setValueAtTime(0.035 / freqs.length, this.ctx.currentTime);
        lfoGain.connect(gain.gain);

        osc.connect(filter);
        filter.connect(gain);
        gain.connect(this.masterGain);

        osc.start();
        lfo.start();
        this.oscillators.push(osc);
      });

      // Smooth fade in
      this.masterGain.gain.linearRampToValueAtTime(0.4, this.ctx.currentTime + 3);
    } catch (err) {
      console.warn('Web Audio ambience failed to start:', err);
    }
  }

  public stopAtmosphere() {
    if (!this.ctx || !this.masterGain || !this.isRunning) return;
    try {
      this.masterGain.gain.linearRampToValueAtTime(0.0001, this.ctx.currentTime + 1.5);
      setTimeout(() => {
        this.oscillators.forEach((osc) => {
          try {
            osc.stop();
            osc.disconnect();
          } catch {
            // Ignore
          }
        });
        this.oscillators = [];
        this.isRunning = false;
      }, 1600);
    } catch (err) {
      console.warn('Error stopping ambient audio:', err);
      this.isRunning = false;
    }
  }

  public playChoiceChime() {
    if (!this.ctx) return;
    try {
      if (this.ctx.state === 'suspended') this.ctx.resume();
      const osc = this.ctx.createOscillator();
      const gain = this.ctx.createGain();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(329.63, this.ctx.currentTime); // E4
      osc.frequency.exponentialRampToValueAtTime(440.0, this.ctx.currentTime + 0.3); // A4

      gain.gain.setValueAtTime(0.05, this.ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.0001, this.ctx.currentTime + 0.6);

      osc.connect(gain);
      gain.connect(this.ctx.destination);
      osc.start();
      osc.stop(this.ctx.currentTime + 0.65);
    } catch {
      // Audio cue is optional
    }
  }

  public playAchievementChime() {
    if (!this.ctx) return;
    try {
      if (this.ctx.state === 'suspended') this.ctx.resume();
      const notes = [220, 277.18, 329.63, 440, 554.37];
      notes.forEach((note, i) => {
        if (!this.ctx) return;
        const osc = this.ctx.createOscillator();
        const gain = this.ctx.createGain();
        osc.type = 'triangle';
        osc.frequency.setValueAtTime(note, this.ctx.currentTime + i * 0.09);

        gain.gain.setValueAtTime(0.06, this.ctx.currentTime + i * 0.09);
        gain.gain.exponentialRampToValueAtTime(0.0001, this.ctx.currentTime + i * 0.09 + 0.7);

        osc.connect(gain);
        gain.connect(this.ctx.destination);
        osc.start(this.ctx.currentTime + i * 0.09);
        osc.stop(this.ctx.currentTime + i * 0.09 + 0.75);
      });
    } catch {
      // Audio cue is optional
    }
  }
}

export const gothicAudio = new GothicSoundEngine();
