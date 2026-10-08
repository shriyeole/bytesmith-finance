import React, { useState } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { LogoIcon } from '../components/common/Icons';

export const LoginPage: React.FC = () => {
  const auth = useAuth();
  const location = useLocation();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [devId, setDevId] = useState('');
  const [isSignUp, setIsSignUp] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const from = (location.state as { from?: string } | null)?.from ?? '/';
  if (auth.user) return <Navigate to={from} replace />;

  const run = async (fn: () => Promise<void>) => {
    setError(null);
    setBusy(true);
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message.replace('Firebase: ', ''));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-page">
      <div className="card auth-card">
        <div className="auth-card__brand"><LogoIcon size={36} /><span>ByteSmiths Finance</span></div>
        <h1 className="auth-card__title">{isSignUp ? 'Create your account' : 'Sign in'}</h1>
        <p className="muted">Your plan, your numbers. Only you can see your data.</p>

        {auth.mode === 'dev' ? (
          <form onSubmit={(e) => { e.preventDefault(); auth.signInDev(devId || 'demo'); }}>
            <div className="callout-box callout-box--neutral"><div className="callout-box__content"><p className="callout-box__sub">Developer mode: no password. Each name is a separate test user.</p></div></div>
            <div className="form-field">
              <label className="form-field__label" htmlFor="dev-id">Test user name</label>
              <input id="dev-id" className="text-input" value={devId} placeholder="demo" onChange={(e) => setDevId(e.target.value)} />
            </div>
            <button type="submit" className="btn btn--primary auth-card__submit">Continue</button>
          </form>
        ) : (
          <>
            <form onSubmit={(e) => { e.preventDefault(); run(() => (isSignUp ? auth.signUpEmail(email, password) : auth.signInEmail(email, password))); }}>
              <div className="form-field">
                <label className="form-field__label" htmlFor="email">Email</label>
                <input id="email" type="email" autoComplete="email" className="text-input" value={email} onChange={(e) => setEmail(e.target.value)} required />
              </div>
              <div className="form-field">
                <label className="form-field__label" htmlFor="password">Password</label>
                <input id="password" type="password" autoComplete={isSignUp ? 'new-password' : 'current-password'} className="text-input" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={8} />
              </div>
              <button type="submit" className="btn btn--primary auth-card__submit" disabled={busy}>{isSignUp ? 'Create account' : 'Sign in'}</button>
            </form>
            <div className="auth-card__divider"><span>or</span></div>
            <button type="button" className="btn btn--outline auth-card__submit" disabled={busy} onClick={() => run(auth.signInGoogle)}>Continue with Google</button>
            <p className="auth-card__switch">
              {isSignUp ? 'Already have an account?' : 'New here?'}{' '}
              <button type="button" className="btn-link" onClick={() => setIsSignUp(!isSignUp)}>{isSignUp ? 'Sign in' : 'Create an account'}</button>
            </p>
          </>
        )}
        {error && <div className="form-alert form-alert--error" role="alert">{error}</div>}
      </div>
    </div>
  );
};
