import React, { useEffect, useState } from 'react';

interface HealthStatus {
  status: string;
  app: string;
  version: string;
}

export const App: React.FC = () => {
  const [backendHealth, setBackendHealth] = useState<HealthStatus | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch('http://localhost:8000/health')
      .then((res) => {
        if (!res.ok) {
          throw new Error(`HTTP error ${res.status}`);
        }
        return res.json();
      })
      .then((data: HealthStatus) => {
        setBackendHealth(data);
        setLoading(false);
      })
      .catch((err: Error) => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  return (
    <div style={{ fontFamily: 'system-ui, sans-serif', padding: '2rem', maxWidth: '800px', margin: '0 auto' }}>
      <h1>ByteSmiths — Personal Finance Copilot</h1>
      <p style={{ color: '#666' }}>
        Deterministic cash-flow modeling, goal feasibility, and scenario testing.
      </p>

      <div style={{ marginTop: '2rem', padding: '1rem', border: '1px solid #e0e0e0', borderRadius: '8px' }}>
        <h3>Backend Health Check</h3>
        {loading && <p>Checking backend connection on port 8000...</p>}
        {error && (
          <p style={{ color: '#d32f2f' }}>
            Backend not reachable ({error}). Start the FastAPI server on port 8000.
          </p>
        )}
        {backendHealth && (
          <div style={{ color: '#2e7d32' }}>
            <p><strong>Status:</strong> {backendHealth.status}</p>
            <p><strong>App:</strong> {backendHealth.app}</p>
            <p><strong>Version:</strong> {backendHealth.version}</p>
          </div>
        )}
      </div>
    </div>
  );
};

export default App;
