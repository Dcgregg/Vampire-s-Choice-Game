import { useEffect, useState } from 'react';
import {
  trustedProgressionQueue,
  TrustedProgressionSnapshot,
} from './trustedProgressionQueue';

export function useTrustedProgression(): TrustedProgressionSnapshot {
  const [snapshot, setSnapshot] = useState(() => trustedProgressionQueue.snapshot());
  useEffect(() => trustedProgressionQueue.subscribe(setSnapshot), []);
  return snapshot;
}

