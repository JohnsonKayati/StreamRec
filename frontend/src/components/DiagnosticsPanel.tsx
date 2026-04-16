import { useStore } from '../store';
import ModelBadge from './ModelBadge';
import RequestHistory from './RequestHistory';

function latencyColor(ms: number): string {
  if (ms < 50) return 'text-green-600';
  if (ms < 200) return 'text-yellow-600';
  return 'text-red-600';
}

interface StatRowProps {
  label: string;
  children: React.ReactNode;
}

function StatRow({ label, children }: StatRowProps) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-gray-100 last:border-0">
      <span className="text-xs font-medium text-gray-500">{label}</span>
      <div className="text-xs font-medium text-gray-900">{children}</div>
    </div>
  );
}

export default function DiagnosticsPanel() {
  const modelName = useStore((s) => s.modelName);
  const latencyMs = useStore((s) => s.latencyMs);
  const servedFromCache = useStore((s) => s.servedFromCache);
  const itemsReturned = useStore((s) => s.itemsReturned);
  const userId = useStore((s) => s.userId);
  const loading = useStore((s) => s.loading);

  const hasData = modelName !== null;

  return (
    <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 space-y-4">
      <h2 className="text-sm font-semibold text-gray-700">System Diagnostics</h2>

      {/* Current request stats */}
      <div className="bg-white border border-gray-200 rounded-md px-3 py-1">
        <StatRow label="Model">
          {loading ? (
            <span className="text-gray-400 italic">Fetching…</span>
          ) : hasData ? (
            <ModelBadge modelName={modelName as 'mf' | 'popularity'} />
          ) : (
            <span className="text-gray-400 italic">—</span>
          )}
        </StatRow>

        <StatRow label="Latency">
          {loading ? (
            <span className="text-gray-400 italic">Fetching…</span>
          ) : latencyMs !== null ? (
            <span className={`font-mono ${latencyColor(latencyMs)}`}>
              {/* Lightning bolt for cache hits */}
              {servedFromCache && (
                <span className="mr-0.5" title="From cache">
                  ⚡
                </span>
              )}
              {latencyMs.toFixed(1)}ms
              {servedFromCache && (
                <span className="ml-1 text-gray-400 font-normal">(cached)</span>
              )}
            </span>
          ) : (
            <span className="text-gray-400 italic">—</span>
          )}
        </StatRow>

        <StatRow label="Cache">
          {loading ? (
            <span className="text-gray-400 italic">Fetching…</span>
          ) : servedFromCache !== null ? (
            <span
              className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium ${
                servedFromCache
                  ? 'bg-green-50 text-green-700 border border-green-200'
                  : 'bg-gray-100 text-gray-600 border border-gray-200'
              }`}
            >
              <span
                className={`w-1.5 h-1.5 rounded-full ${
                  servedFromCache ? 'bg-green-500' : 'bg-gray-400'
                }`}
              />
              {servedFromCache ? 'HIT' : 'MISS'}
            </span>
          ) : (
            <span className="text-gray-400 italic">—</span>
          )}
        </StatRow>

        <StatRow label="Items returned">
          {loading ? (
            <span className="text-gray-400 italic">Fetching…</span>
          ) : itemsReturned !== null ? (
            <span className="font-mono">{itemsReturned}</span>
          ) : (
            <span className="text-gray-400 italic">—</span>
          )}
        </StatRow>

        <StatRow label="User ID">
          {userId ? (
            <span className="font-mono text-gray-700 max-w-[130px] truncate inline-block">
              {userId}
            </span>
          ) : (
            <span className="text-gray-400 italic">—</span>
          )}
        </StatRow>
      </div>

      {/* Divider */}
      <div className="border-t border-gray-200" />

      {/* Request history */}
      <div>
        <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
          Request History
        </h3>
        <RequestHistory />
        {/* Teaching note about cache hit pattern */}
        <p className="mt-2 text-xs text-gray-400 leading-relaxed">
          Tip: query the same user twice to observe cache HIT on the second
          request.
        </p>
      </div>
    </div>
  );
}
