
const EARTH_RADIUS_KM = 6371;
function toRadians(degrees: number): number {
  return (degrees * Math.PI) / 180;
}
export function isValidCoordinate(lat: unknown, lon: unknown): boolean {
  if (typeof lat !== 'number' || typeof lon !== 'number') return false;
  if (isNaN(lat) || isNaN(lon)) return false;
  if (!isFinite(lat) || !isFinite(lon)) return false;
  return lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180;
}
export function calculateDistanceKm(
  lat1: number | null | undefined,
  lon1: number | null | undefined,
  lat2: number | null | undefined,
  lon2: number | null | undefined
): number | null {
  if (!isValidCoordinate(lat1, lon1) || !isValidCoordinate(lat2, lon2)) {
    return null;
  }
  const validLat1 = lat1 as number;
  const validLon1 = lon1 as number;
  const validLat2 = lat2 as number;
  const validLon2 = lon2 as number;
  if (validLat1 === validLat2 && validLon1 === validLon2) {
    return 0;
  }
  const dLat = toRadians(validLat2 - validLat1);
  const dLon = toRadians(validLon2 - validLon1);
  const rLat1 = toRadians(validLat1);
  const rLat2 = toRadians(validLat2);
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos(rLat1) * Math.cos(rLat2) * Math.sin(dLon / 2) * Math.sin(dLon / 2);
  const clampedA = Math.max(0, Math.min(1, a));
  const c = 2 * Math.atan2(Math.sqrt(clampedA), Math.sqrt(1 - clampedA));
  const distance = EARTH_RADIUS_KM * c;
  if (isNaN(distance) || !isFinite(distance)) {
    return null;
  }
  return Math.round(distance * 10) / 10;
}
export function formatCoordinates(
  lat: number | null | undefined,
  lon: number | null | undefined
): string {
  if (!isValidCoordinate(lat, lon)) {
    return 'Coordinates Unavailable';
  }
  const latNum = lat as number;
  const lonNum = lon as number;
  const latDir = latNum >= 0 ? 'N' : 'S';
  const lonDir = lonNum >= 0 ? 'E' : 'W';
  const latFormatted = Math.abs(latNum).toFixed(4);
  const lonFormatted = Math.abs(lonNum).toFixed(4);
  return `${latFormatted}° ${latDir}, ${lonFormatted}° ${lonDir}`;
}
export function formatDistance(distanceKm: number | null | undefined): string {
  if (distanceKm == null || isNaN(distanceKm) || !isFinite(distanceKm)) {
    return '—';
  }
  return `${distanceKm.toFixed(1)} km`;
}
