import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { Auth, User as FirebaseUser } from 'firebase/auth';

export type AuthMode = 'dev' | 'firebase';
export const AUTH_MODE: AuthMode = import.meta.env.VITE_AUTH_MODE === 'firebase' ? 'firebase' : 'dev';

export interface SessionUser {
  uid: string;
  email: string | null;
  displayName: string | null;
}

interface AuthContextValue {
  mode: AuthMode;
  user: SessionUser | null;
  ready: boolean;
  getToken: () => Promise<string | null>;
  signInDev: (devId: string) => void;
  signInEmail: (email: string, password: string) => Promise<void>;
  signUpEmail: (email: string, password: string) => Promise<void>;
  signInGoogle: () => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);
const DEV_KEY = 'bytesmith.devUser';

let authPromise: Promise<Auth> | null = null;
function getFirebaseAuth(): Promise<Auth> {
  // Loaded lazily so dev mode never downloads or needs Firebase config.
  if (!authPromise) {
    authPromise = (async () => {
      const [{ initializeApp }, { getAuth }] = await Promise.all([import('firebase/app'), import('firebase/auth')]);
      const app = initializeApp({
        apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
        authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
        projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
      });
      return getAuth(app);
    })();
  }
  return authPromise;
}

function toSession(u: FirebaseUser): SessionUser {
  return { uid: u.uid, email: u.email, displayName: u.displayName };
}

function readDevUser(): string | null {
  try {
    return localStorage.getItem(DEV_KEY);
  } catch {
    return null;
  }
}

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<SessionUser | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (AUTH_MODE === 'dev') {
      const id = readDevUser();
      setUser(id ? { uid: id, email: null, displayName: id } : null);
      setReady(true);
      return;
    }
    let unsub: (() => void) | undefined;
    getFirebaseAuth().then(async (auth) => {
      const { onAuthStateChanged } = await import('firebase/auth');
      unsub = onAuthStateChanged(auth, (u) => {
        setUser(u ? toSession(u) : null);
        setReady(true);
      });
    });
    return () => unsub?.();
  }, []);

  const getToken = useCallback(async () => {
    if (AUTH_MODE === 'dev') {
      const id = readDevUser();
      return id ? `dev:${id}` : null;
    }
    const auth = await getFirebaseAuth();
    return auth.currentUser ? auth.currentUser.getIdToken() : null;
  }, []);

  const value = useMemo<AuthContextValue>(() => ({
    mode: AUTH_MODE,
    user,
    ready,
    getToken,
    signInDev: (devId: string) => {
      const id = devId.trim().toLowerCase().replace(/[^a-z0-9_-]/g, '-').slice(0, 64);
      if (!id) return;
      try {
        localStorage.setItem(DEV_KEY, id);
      } catch {
        /* storage blocked: session-only login */
      }
      setUser({ uid: id, email: null, displayName: id });
    },
    signInEmail: async (email, password) => {
      const { signInWithEmailAndPassword } = await import('firebase/auth');
      await signInWithEmailAndPassword(await getFirebaseAuth(), email, password);
    },
    signUpEmail: async (email, password) => {
      const { createUserWithEmailAndPassword } = await import('firebase/auth');
      await createUserWithEmailAndPassword(await getFirebaseAuth(), email, password);
    },
    signInGoogle: async () => {
      const { GoogleAuthProvider, signInWithPopup } = await import('firebase/auth');
      await signInWithPopup(await getFirebaseAuth(), new GoogleAuthProvider());
    },
    signOut: async () => {
      if (AUTH_MODE === 'dev') {
        try {
          localStorage.removeItem(DEV_KEY);
        } catch {
          /* ignore */
        }
        setUser(null);
        return;
      }
      const { signOut } = await import('firebase/auth');
      await signOut(await getFirebaseAuth());
    },
  }), [user, ready, getToken]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}
