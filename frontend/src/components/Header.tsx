import { useStore } from '../store';

export default function Header() {
  const isHealthy = useStore((s) => s.isHealthy);

  return (
    <header className="bg-white border-b border-gray-200">
      <div className="w-full max-w-[1600px] mx-auto px-4 sm:px-6 lg:px-10 xl:px-14 py-4 flex items-center justify-between">
        {/* Logo + tagline */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            {/* StreamRec logo mark */}
            <div className="w-7 h-7 bg-blue-600 rounded-md flex items-center justify-center flex-shrink-0">
              <svg
                className="w-4 h-4 text-white"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
                strokeWidth={2}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M3 7l6 6-6 6M13 5h8M13 12h8M13 19h8"
                />
              </svg>
            </div>
            <span className="text-lg font-semibold text-gray-900">
              StreamRec
            </span>
          </div>
          <span className="hidden sm:block text-gray-300 select-none">·</span>
          <span className="hidden sm:block text-sm text-gray-500">
            Real-time ML Recommendations
          </span>
        </div>

        {/* Health indicator */}
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-500 hidden sm:inline">
            {isHealthy ? 'Connected' : 'Disconnected'}
          </span>
          <div className="relative group">
            <div
              className={`w-2.5 h-2.5 rounded-full transition-colors duration-300 ${
                isHealthy ? 'bg-green-500' : 'bg-red-500'
              }`}
            />
            {/* Pulse ring when healthy */}
            {isHealthy && (
              <div className="absolute inset-0 rounded-full bg-green-400 opacity-40 animate-ping" />
            )}
            {/* Tooltip */}
            <div className="absolute right-0 top-full mt-2 px-2 py-1 text-xs bg-gray-900 text-white rounded opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap pointer-events-none z-10">
              {isHealthy
                ? 'Backend connected'
                : 'Backend unreachable — is port 8002 running?'}
            </div>
          </div>
        </div>
      </div>
    </header>
  );
}
