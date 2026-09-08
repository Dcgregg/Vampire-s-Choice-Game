import React, { useState } from 'react';
import { usePWAInstall } from '../../hooks/usePWAInstall';
import { Download, Share, Plus, X } from 'lucide-react';

export const PWAInstallButton: React.FC<{ compact?: boolean }> = ({ compact = false }) => {
  const { isInstallable, isInstalled, isIOS, install } = usePWAInstall();
  const [showIOSModal, setShowIOSModal] = useState(false);

  if (isInstalled) return null;

  if (isInstallable) {
    return (
      <button
        id="pwa-install-btn"
        onClick={install}
        className={`inline-flex items-center gap-2 rounded-full border border-[#c5a059]/40 bg-[#191122]/90 text-[#f5f0e6] transition-all duration-300 hover:border-[#c5a059] hover:bg-[#251833] active:scale-95 shadow-md ${
          compact ? 'px-2.5 py-1 text-xs' : 'px-3 py-1.5 text-xs'
        }`}
        title="Install Vampire's Choice as an App"
      >
        <Download className="w-3.5 h-3.5 text-[#e5c158]" />
        <span className="font-interface font-medium">Install App</span>
      </button>
    );
  }

  if (isIOS) {
    return (
      <>
        <button
          id="pwa-install-ios-btn"
          onClick={() => setShowIOSModal(true)}
          className={`inline-flex items-center gap-1.5 rounded-full border border-[#c5a059]/30 bg-[#160f20]/90 text-[#ede5d8] transition-all hover:border-[#c5a059]/80 text-xs ${
            compact ? 'px-2 py-1' : 'px-3 py-1.5'
          }`}
          title="Install on iOS"
        >
          <Share className="w-3.5 h-3.5 text-[#e5c158]" />
          <span className="font-interface font-medium">Add to Home</span>
        </button>

        {showIOSModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 backdrop-blur-sm">
            <div className="relative w-full max-w-sm rounded-2xl border border-[#c5a059]/40 bg-[#120d18] p-6 shadow-2xl text-[#ede5d8]">
              <button
                onClick={() => setShowIOSModal(false)}
                className="absolute top-4 right-4 rounded-full p-1 text-[#d6cbbe] hover:bg-white/10"
              >
                <X className="w-5 h-5" />
              </button>

              <div className="flex items-center gap-3 mb-4">
                <div className="w-10 h-10 rounded-xl bg-rose-950/80 border border-rose-800/50 flex items-center justify-center">
                  <span className="text-xl">🩸</span>
                </div>
                <div>
                  <h3 className="font-display font-semibold text-base text-[#f5f0e6]">
                    Install Vampire's Choice
                  </h3>
                  <p className="text-xs text-[#a89ba5]">Progressive Web App on iOS</p>
                </div>
              </div>

              <div className="space-y-3 text-sm text-[#d6cbbe]">
                <div className="flex items-start gap-3 rounded-lg bg-black/40 p-3 border border-white/5">
                  <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-rose-900/60 text-xs font-semibold text-rose-200">
                    1
                  </span>
                  <p className="text-xs leading-relaxed">
                    Tap the <strong className="text-white">Share</strong> icon at the bottom of
                    Safari (<Share className="inline w-3.5 h-3.5 text-[#e5c158]" />).
                  </p>
                </div>

                <div className="flex items-start gap-3 rounded-lg bg-black/40 p-3 border border-white/5">
                  <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-rose-900/60 text-xs font-semibold text-rose-200">
                    2
                  </span>
                  <p className="text-xs leading-relaxed">
                    Scroll down and select{' '}
                    <strong className="text-white">Add to Home Screen</strong> (
                    <Plus className="inline w-3.5 h-3.5 text-[#e5c158]" />
                    ).
                  </p>
                </div>
              </div>

              <button
                onClick={() => setShowIOSModal(false)}
                className="mt-5 w-full rounded-xl bg-gradient-to-r from-rose-900 to-rose-800 py-2.5 text-xs font-semibold uppercase tracking-wider text-white shadow-lg transition hover:from-rose-800 hover:to-rose-700"
              >
                Done
              </button>
            </div>
          </div>
        )}
      </>
    );
  }

  return null;
};
