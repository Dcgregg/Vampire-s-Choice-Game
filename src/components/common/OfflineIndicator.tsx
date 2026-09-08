import React from 'react';
import { useOnlineStatus } from '../../hooks/useOnlineStatus';
import { WifiOff } from 'lucide-react';

export const OfflineIndicator: React.FC = () => {
  const isOnline = useOnlineStatus();

  if (isOnline) return null;

  return (
    <div className="fixed top-16 left-1/2 z-50 -translate-x-1/2 flex items-center gap-2 rounded-full border border-amber-800/60 bg-[#1e130d] px-3.5 py-1.5 text-xs font-medium text-amber-200 shadow-lg backdrop-blur-md">
      <WifiOff className="h-3.5 w-3.5 text-amber-400" />
      <span>Offline Archive Active — Reading from local memory</span>
    </div>
  );
};
