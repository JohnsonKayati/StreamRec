import { useEffect } from 'react';
import { useStore } from './store';
import Header from './components/Header';
import ControlBar from './components/ControlBar';
import ErrorBanner from './components/ErrorBanner';
import RecommendationPanel from './components/RecommendationPanel';
import DiagnosticsPanel from './components/DiagnosticsPanel';

const HEALTH_POLL_INTERVAL_MS = 30_000;

export default function App() {
  const checkHealth = useStore((s) => s.checkHealth);

  // Poll health on mount and every 30 seconds
  useEffect(() => {
    checkHealth();
    const id = setInterval(checkHealth, HEALTH_POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [checkHealth]);

  return (
    <div className="min-h-screen bg-gray-50">
      <Header />

      <main className="w-full max-w-[1600px] mx-auto px-4 sm:px-6 lg:px-10 xl:px-14 py-6 space-y-4">
        {/* Control bar */}
        <ControlBar />

        {/* Error banner — sits between controls and results */}
        <ErrorBanner />

        {/* Two-column layout */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 items-start">
          {/* Recommendations — 2/3 width */}
          <div className="lg:col-span-2 min-w-0">
            <RecommendationPanel />
          </div>

          {/* Diagnostics — 1/3 width */}
          <div className="lg:col-span-1">
            <DiagnosticsPanel />
          </div>
        </div>
      </main>
    </div>
  );
}
