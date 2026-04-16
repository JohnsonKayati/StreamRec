import { useState, useCallback } from 'react';
import { useStore } from '../store';

// Hardcoded list of ~20 known user IDs that exist in the synthetic training data
const KNOWN_USER_IDS = [
  'user_0001', 'user_0002', 'user_0003', 'user_0004', 'user_0005',
  'user_0006', 'user_0007', 'user_0008', 'user_0009', 'user_0010',
  'user_0011', 'user_0012', 'user_0013', 'user_0014', 'user_0015',
  'user_0016', 'user_0017', 'user_0018', 'user_0019', 'user_0020',
];

function getRandomKnownUser(): string {
  return KNOWN_USER_IDS[Math.floor(Math.random() * KNOWN_USER_IDS.length)];
}

export default function ControlBar() {
  const setUserId = useStore((s) => s.setUserId);
  const setK = useStore((s) => s.setK);
  const fetchRecommendations = useStore((s) => s.fetchRecommendations);
  const loading = useStore((s) => s.loading);
  const error = useStore((s) => s.error);
  const errorType = useStore((s) => s.errorType);

  const [localUserId, setLocalUserId] = useState('');
  const [localK, setLocalK] = useState(10);

  const handleSubmit = useCallback(() => {
    setUserId(localUserId);
    setK(localK);
    fetchRecommendations();
  }, [localUserId, localK, setUserId, setK, fetchRecommendations]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') handleSubmit();
  };

  const applyQuickPick = useCallback(
    (userId: string) => {
      setLocalUserId(userId);
      setUserId(userId);
      setK(localK);
      fetchRecommendations();
    },
    [localK, setUserId, setK, fetchRecommendations],
  );

  const inlineError = errorType === '422' ? error : null;

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-5">
      {/* Main row: input + k + button */}
      <div className="flex flex-col sm:flex-row gap-3">
        {/* User ID input */}
        <div className="flex-1 min-w-0">
          <label
            htmlFor="userId"
            className="block text-xs font-medium text-gray-500 mb-1"
          >
            User ID
          </label>
          <input
            id="userId"
            type="text"
            value={localUserId}
            onChange={(e) => setLocalUserId(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="e.g. user_0042"
            disabled={loading}
            className={`w-full px-3 py-2 text-sm font-mono border rounded-md bg-white placeholder-gray-400 text-gray-900
              focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent
              disabled:opacity-50 disabled:cursor-not-allowed
              transition-colors duration-150
              ${inlineError ? 'border-red-400 bg-red-50' : 'border-gray-300 hover:border-gray-400'}`}
          />
          {inlineError && (
            <p className="mt-1 text-xs text-red-600">{inlineError}</p>
          )}
        </div>

        {/* K selector */}
        <div className="sm:w-40">
          <label
            htmlFor="kValue"
            className="block text-xs font-medium text-gray-500 mb-1"
          >
            Results (k = {localK})
          </label>
          <input
            id="kValue"
            type="range"
            min={1}
            max={50}
            value={localK}
            onChange={(e) => setLocalK(Number(e.target.value))}
            disabled={loading}
            className="w-full h-2 bg-gray-200 rounded-full appearance-none cursor-pointer accent-blue-600 disabled:opacity-50 disabled:cursor-not-allowed mt-2"
          />
        </div>

        {/* Submit button */}
        <div className="sm:self-end">
          <button
            onClick={handleSubmit}
            disabled={loading}
            className="w-full sm:w-auto px-5 py-2 bg-blue-600 text-white text-sm font-medium rounded-md
              hover:bg-blue-700 active:bg-blue-800
              disabled:opacity-50 disabled:cursor-not-allowed
              transition-colors duration-150
              flex items-center justify-center gap-2"
          >
            {loading ? (
              <>
                <svg
                  className="w-4 h-4 animate-spin"
                  fill="none"
                  viewBox="0 0 24 24"
                >
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                  />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                  />
                </svg>
                Loading…
              </>
            ) : (
              'Get Recommendations'
            )}
          </button>
        </div>
      </div>

      {/* Quick picks row */}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <span className="text-xs text-gray-400 font-medium">Quick picks:</span>
        <button
          onClick={() => applyQuickPick('user_0001')}
          disabled={loading}
          className="px-3 py-1 text-xs font-medium rounded-full border border-blue-200 text-blue-700 bg-blue-50
            hover:bg-blue-100 active:ring-2 active:ring-blue-300
            disabled:opacity-50 disabled:cursor-not-allowed
            transition-colors duration-150"
        >
          Known User
        </button>
        <button
          onClick={() => applyQuickPick('user_9999')}
          disabled={loading}
          className="px-3 py-1 text-xs font-medium rounded-full border border-amber-200 text-amber-700 bg-amber-50
            hover:bg-amber-100 active:ring-2 active:ring-amber-300
            disabled:opacity-50 disabled:cursor-not-allowed
            transition-colors duration-150"
        >
          Cold Start
        </button>
        <button
          onClick={() => applyQuickPick(getRandomKnownUser())}
          disabled={loading}
          className="px-3 py-1 text-xs font-medium rounded-full border border-gray-200 text-gray-600 bg-white
            hover:bg-gray-50 active:ring-2 active:ring-gray-300
            disabled:opacity-50 disabled:cursor-not-allowed
            transition-colors duration-150"
        >
          Random Known
        </button>
      </div>
    </div>
  );
}
