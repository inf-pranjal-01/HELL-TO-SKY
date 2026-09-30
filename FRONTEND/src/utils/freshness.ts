export type FreshnessStatus = 'LIVE' | 'DATA DELAYED' | 'DATA STALE' | 'MONITORING PAUSED';
export interface FreshnessState {
  status: FreshnessStatus;
  secondsAgo: number;
  label: string;
}
export function calculateFreshness(
  timestamp: string | Date | null | undefined,
  isPaused: boolean = false,
  pollIntervalSeconds: number = 30 * 60
): FreshnessState {
  if (isPaused) {
    return {
      status: 'MONITORING PAUSED',
      secondsAgo: 0,
      label: 'MONITORING PAUSED',
    };
  }
  if (!timestamp) {
    return {
      status: 'DATA STALE',
      secondsAgo: Infinity,
      label: 'DATA UNAVAILABLE',
    };
  }
  const timeMs = typeof timestamp === 'string' ? new Date(timestamp).getTime() : timestamp.getTime();
  const diffMs = Math.max(0, Date.now() - timeMs);
  const secondsAgo = Math.floor(diffMs / 1000);
  if (secondsAgo <= pollIntervalSeconds) {
    return {
      status: 'LIVE',
      secondsAgo,
      label: `NEXT PROVIDER CHECK IN ${Math.max(0, Math.ceil((pollIntervalSeconds - secondsAgo) / 60))}M`,
    };
  }
  if (secondsAgo <= pollIntervalSeconds * 2) {
    return {
      status: 'DATA DELAYED',
      secondsAgo,
      label: 'PROVIDER CHECK DELAYED',
    };
  }
  return {
    status: 'DATA STALE',
    secondsAgo,
    label: 'DATA STALE',
  };
}
