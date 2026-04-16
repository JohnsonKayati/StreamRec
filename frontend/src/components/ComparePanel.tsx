import { useEffect, useState, useCallback } from 'react';
import { useStore } from '../store';
import { fetchRecommendationsApi } from '../api';
import type { ApiResponse } from '../types';
import ModelBadge from './ModelBadge';
import RecommendationCard from './RecommendationCard';
import SkeletonCard from './SkeletonCard';

const MF_USER = 'user_0001';
const POP_USER = 'user_9999';

interface SideState {
  data: ApiResponse | null;
  loading: boolean;
  error: string | null;
}

const IDLE: SideState = { data: null, loading: false, error: null };

interface CompareSideProps {
  label: string;
  userId: string;
  side: SideState;
  k: number;
}

function CompareSide({ label, userId, side, k }: CompareSideProps) {
  const { data, loading, error } = side;

  const maxScore =
    data && data.recommendations.length > 0
      ? Math.max(...data.recommendations.map((r) => r.score))
      : 1;

  return (
    <div className="flex flex-col min-w-0">
      {/* Column header */}
      <div className="flex items-center justify-between mb-3">
        <div>
          <div className="text-sm font-semibold text-gray-900">{label}</div>
          <div className="font-mono text-xs text-gray-400 mt-0.5">{userId}</div>
        </div>
        {data && !loading && <ModelBadge modelName={data.model_name} />}
      </div>

      {/* Metadata bar when data available */}
      {data && !loading && (
        <div className="flex items-center gap-3 mb-3 px-2.5 py-1.5 bg-gray-50 border border-gray-200 rounded-md text-xs text-gray-500">
          <span>
            Latency:{' '}
            <span className="font-mono text-gray-700">
              {data.latency_ms.toFixed(1)}ms
            </span>
          </span>
          <span className="text-gray-300">·</span>
          <span
            className={`font-medium ${
              data.served_from_cache ? 'text-green-600' : 'text-gray-500'
            }`}
          >
            {data.served_from_cache ? '⚡ Cached' : 'Cache MISS'}
          </span>
          <span className="text-gray-300">·</span>
          <span>{data.recommendations.length} items</span>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="px-3 py-2 bg-red-50 border border-red-200 rounded-md text-xs text-red-700 mb-3">
          {error}
        </div>
      )}

      {/* Skeletons */}
      {loading && (
        <div className="space-y-2">
          {Array.from({ length: k }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      )}

      {/* Cards */}
      {!loading && data && data.recommendations.length > 0 && (
        <div className="space-y-2">
          {data.recommendations.map((rec) => (
            <RecommendationCard
              key={rec.item_id}
              recommendation={rec}
              maxScore={maxScore}
              modelName={data.model_name}
            />
          ))}
        </div>
      )}

      {!loading && data && data.recommendations.length === 0 && (
        <div className="py-8 text-center text-sm text-gray-400">
          No recommendations returned
        </div>
      )}
    </div>
  );
}

export default function ComparePanel() {
  const k = useStore((s) => s.k);

  const [mfSide, setMfSide] = useState<SideState>(IDLE);
  const [popSide, setPopSide] = useState<SideState>(IDLE);

  const fetchBoth = useCallback(async () => {
    setMfSide({ data: null, loading: true, error: null });
    setPopSide({ data: null, loading: true, error: null });

    const [mfResult, popResult] = await Promise.allSettled([
      fetchRecommendationsApi(MF_USER, k),
      fetchRecommendationsApi(POP_USER, k),
    ]);

    setMfSide({
      data: mfResult.status === 'fulfilled' ? mfResult.value : null,
      loading: false,
      error:
        mfResult.status === 'rejected'
          ? 'Failed to load MF recommendations'
          : null,
    });

    setPopSide({
      data: popResult.status === 'fulfilled' ? popResult.value : null,
      loading: false,
      error:
        popResult.status === 'rejected'
          ? 'Failed to load popularity recommendations'
          : null,
    });
  }, [k]);

  // Auto-fetch on mount and whenever k changes
  useEffect(() => {
    fetchBoth();
  }, [fetchBoth]);

  const isLoading = mfSide.loading || popSide.loading;

  return (
    <div>
      {/* Compare header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-base font-semibold text-gray-900">
            Side-by-side Comparison
          </h2>
          <p className="text-xs text-gray-500 mt-0.5">
            Both models queried simultaneously — same catalog, different
            personalisation
          </p>
        </div>
        <button
          onClick={fetchBoth}
          disabled={isLoading}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-gray-200 rounded-md bg-white text-gray-600
            hover:bg-gray-50 hover:border-gray-300 active:bg-gray-100
            disabled:opacity-50 disabled:cursor-not-allowed
            transition-colors duration-150"
        >
          {isLoading ? (
            <>
              <svg className="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              Fetching…
            </>
          ) : (
            <>
              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              Refresh
            </>
          )}
        </button>
      </div>

      {/* Two-column layout — stacked on mobile, side-by-side on lg+ */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
        <div className="bg-white border border-blue-100 rounded-lg p-4">
          <CompareSide
            label="Personalized (MF)"
            userId={MF_USER}
            side={mfSide}
            k={k}
          />
        </div>
        <div className="bg-white border border-amber-100 rounded-lg p-4">
          <CompareSide
            label="Popularity Fallback"
            userId={POP_USER}
            side={popSide}
            k={k}
          />
        </div>
      </div>
    </div>
  );
}
