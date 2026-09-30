import { TrendPoint } from '../types';
export function windowTrendPoints(
  points: TrendPoint[],
  hours: number
): { points: TrendPoint[]; windowStart: number; windowEnd: number } {
  const spanMs = Math.max(hours, 1) * 60 * 60 * 1000;
  if (!points || points.length === 0) {
    const windowEnd = Date.now();
    return { points: [], windowStart: windowEnd - spanMs, windowEnd };
  }
  const sorted = [...points]
    .filter((p) => p && p.timestamp && !Number.isNaN(new Date(p.timestamp).getTime()))
    .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());
  if (sorted.length === 0) {
    const windowEnd = Date.now();
    return { points: [], windowStart: windowEnd - spanMs, windowEnd };
  }
  const lastTime = new Date(sorted[sorted.length - 1].timestamp).getTime();
  const windowEnd = lastTime;
  const windowStart = windowEnd - spanMs;
  const inWindow = sorted.filter((p) => {
    const t = new Date(p.timestamp).getTime();
    return t >= windowStart && t <= windowEnd;
  });
  const pointByTime = new Map<number, TrendPoint>();
  for (const point of inWindow) {
    const time = new Date(point.timestamp).getTime();
    const existing = pointByTime.get(time);
    pointByTime.set(time, existing ? { ...existing, ...point } : point);
  }
  const deduped = Array.from(pointByTime.entries())
    .sort(([left], [right]) => left - right)
    .map(([, point]) => point);
  return {
    points: deduped,
    windowStart,
    windowEnd,
  };
}
