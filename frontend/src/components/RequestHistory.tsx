import { useStore } from '../store';

export default function RequestHistory() {
  const requestHistory = useStore((s) => s.requestHistory);

  if (requestHistory.length === 0) {
    return (
      <div className="text-xs text-gray-400 italic">No requests yet</div>
    );
  }

  return (
    <div className="space-y-1.5">
      {requestHistory.map((entry, i) => (
        <div
          key={entry.timestamp}
          className={`flex items-center justify-between text-xs py-1.5 px-2 rounded ${
            i === 0 ? 'bg-white border border-gray-200' : 'text-gray-500'
          }`}
        >
          <div className="flex items-center gap-1.5 min-w-0">
            <span className="font-mono text-gray-700 truncate max-w-[90px]">
              {entry.userId}
            </span>
            <span className="text-gray-400">→</span>
            <span
              className={`font-medium ${
                entry.modelName === 'mf' ? 'text-blue-600' : 'text-amber-600'
              }`}
            >
              {entry.modelName}
            </span>
          </div>

          <div className="flex items-center gap-1.5 flex-shrink-0 ml-2">
            <span className="font-mono text-gray-500">
              {entry.latencyMs.toFixed(0)}ms
            </span>
            <span
              className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                entry.cached ? 'bg-green-500' : 'bg-gray-300'
              }`}
              title={entry.cached ? 'Cache HIT' : 'Cache MISS'}
            />
          </div>
        </div>
      ))}
    </div>
  );
}
