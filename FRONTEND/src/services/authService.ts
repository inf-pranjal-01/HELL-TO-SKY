import { User, LoginCredentials, AuthResponse } from '../types/auth';
const SESSION_STORAGE_KEY = 'skyguard_mock_session';
const DEMO_EMAIL = 'demo@skyguard.local';
const DEMO_PASSWORD = 'demo1234';
const MOCK_USER: User = {
  id: 'usr-demo-001',
  email: 'demo@skyguard.local',
  name: 'SkyGuard Demo Operator',
  role: 'Administrator',
  stationAccess: ['ST-NDL-001', 'ST-MUM-002', 'ST-BLR-003', 'ST-HYD-004'],
  lastLogin: new Date().toISOString(),
};
export const authService = {
  async login(credentials: LoginCredentials): Promise<AuthResponse> {
    return new Promise((resolve) => {
      setTimeout(() => {
        const cleanEmail = credentials.email.trim().toLowerCase();
        if (cleanEmail === DEMO_EMAIL && credentials.password === DEMO_PASSWORD) {
          const userSession: User = {
            ...MOCK_USER,
            lastLogin: new Date().toISOString(),
          };
          this.setStoredSession(userSession, !!credentials.rememberMe);
          resolve({
            success: true,
            user: userSession,
            message: 'Authentication successful.',
          });
        } else {
          resolve({
            success: false,
            message: 'Invalid demo credentials. Please use demo@skyguard.local and password demo1234.',
          });
        }
      }, 300);
    });
  },
  async logout(): Promise<void> {
    return new Promise((resolve) => {
      setTimeout(() => {
        this.clearSession();
        resolve();
      }, 100);
    });
  },
  getStoredSession(): User | null {
    try {
      const sessionData = sessionStorage.getItem(SESSION_STORAGE_KEY);
      if (sessionData) {
        return JSON.parse(sessionData) as User;
      }
      const localData = localStorage.getItem(SESSION_STORAGE_KEY);
      if (localData) {
        return JSON.parse(localData) as User;
      }
    } catch {
      this.clearSession();
    }
    return null;
  },
  setStoredSession(user: User, rememberMe: boolean): void {
    const dataStr = JSON.stringify(user);
    this.clearSession();
    if (rememberMe) {
      localStorage.setItem(SESSION_STORAGE_KEY, dataStr);
    } else {
      sessionStorage.setItem(SESSION_STORAGE_KEY, dataStr);
    }
  },
  clearSession(): void {
    sessionStorage.removeItem(SESSION_STORAGE_KEY);
    localStorage.removeItem(SESSION_STORAGE_KEY);
  },
  isAuthenticated(): boolean {
    return this.getStoredSession() !== null;
  },
};
