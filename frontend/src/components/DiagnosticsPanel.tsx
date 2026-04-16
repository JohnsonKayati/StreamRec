import { useState } from 'react';
import { useStore } from '../store';
import ModelBadge from './ModelBadge';
import RequestHistory from './RequestHistory';
import LatencySparkline from './LatencySparkline';
import LatencyModal from './LatencyModal';

function latencyColor(ms: number): string {
  if (ms < 5) return 'text-green-600';
  if (ms < 20) return 'text-yellow-600';
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
  const latencyHistory = useStore((s) => s.latencyHistory);

  const [modalOpen, setModalOpen] = useState(false);

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

      {/* Latency sparkline — clickable to expand */}
      <div>
        <div
          role="button"
          tabIndex={0}
          onClick={() => setModalOpen(true)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') setModalOpen(true);
          }}
          className="cursor-pointer rounded-md -mx-1 px-1 py-1 transition-colors hover:bg-gray-100 group"
        >
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
              Latency History
            </h3>
            <svg
              className="w-3.5 h-3.5 text-gray-300 group-hover:text-gray-500 transition-colors flex-shrink-0"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              strokeWidth={2}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5v-4m0 4h-4m4 0l-5-5"
              />
            </svg>
          </div>
          <LatencySparkline history={latencyHistory} />
          <p className="mt-1.5 text-xs text-gray-400 leading-relaxed">
            Spikes = cache MISS. Flat near-zero = cache HIT. Click to expand.
          </p>
        </div>
      </div>

      <div className="border-t border-gray-200" />

      {/* Offline Evaluation */}
      <div>
        <div className="flex items-center gap-1.5 mb-2">
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
            Offline Evaluation
          </h3>
          <span
            title="Metrics computed offline on held-out validation data. Not real-time."
            className="flex-shrink-0 text-gray-300 hover:text-gray-500 cursor-help transition-colors"
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </span>
        </div>

        <div className="space-y-2">
          {/* Popularity */}
          <div className="bg-white border border-gray-200 rounded-md px-3 py-2.5">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-medium text-amber-700 bg-amber-50 border border-amber-200 px-1.5 py-0.5 rounded">
                Popularity
              </span>
              <span className="text-xs text-gray-400">baseline</span>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <div className="text-xs text-gray-400 mb-0.5">NDCG@10</div>
                <div className="font-mono text-sm font-semibold text-gray-700">0.2412</div>
              </div>
              <div>
                <div className="text-xs text-gray-400 mb-0.5">Recall@10</div>
                <div className="font-mono text-sm font-semibold text-gray-700">0.2100</div>
              </div>
            </div>
          </div>

          {/* MF */}
          <div className="bg-white border border-blue-100 rounded-md px-3 py-2.5">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-medium text-blue-700 bg-blue-50 border border-blue-200 px-1.5 py-0.5 rounded">
                Matrix Factorization
              </span>
              <span className="text-xs font-medium text-green-700 bg-green-50 border border-green-200 px-1.5 py-0.5 rounded">
                +39% NDCG
              </span>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <div className="text-xs text-gray-400 mb-0.5">NDCG@10</div>
                <div className="font-mono text-sm font-semibold text-blue-700">0.3351</div>
              </div>
              <div>
                <div className="text-xs text-gray-400 mb-0.5">Recall@10</div>
                <div className="font-mono text-sm font-semibold text-blue-700">0.3732</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="border-t border-gray-200" />

      {/* Request history */}
      <div>
        <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
          Request History
        </h3>
        <RequestHistory />
        <p className="mt-2 text-xs text-gray-400 leading-relaxed">
          Tip: query the same user twice to observe cache HIT on the second
          request.
        </p>
      </div>

      {modalOpen && (
        <LatencyModal
          history={latencyHistory}
          onClose={() => setModalOpen(false)}
        />
      )}
    </div>
  );
}
