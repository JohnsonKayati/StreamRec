import { useStore } from '../store';
import ModelBadge from './ModelBadge';
import RecommendationCard from './RecommendationCard';
import SkeletonCard from './SkeletonCard';

export default function RecommendationPanel() {
  const recommendations = useStore((s) => s.recommendations);
  const modelName = useStore((s) => s.modelName);
  const loading = useStore((s) => s.loading);
  const k = useStore((s) => s.k);

  const maxScore =
    recommendations.length > 0
      ? Math.max(...recommendations.map((r) => r.score))
      : 1;

  const hasResults = recommendations.length > 0;

  // Empty state — no request made yet
  if (!loading && !hasResults && modelName === null) {
    return (
      <div className="bg-white border border-gray-200 rounded-lg flex flex-col items-center justify-center py-20 px-6 text-center">
        <div className="w-12 h-12 bg-gray-100 rounded-full flex items-center justify-center mb-4">
          <svg
            className="w-6 h-6 text-gray-400"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
            strokeWidth={1.5}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0112 15a9.065 9.065 0 00-6.23-.693L5 14.5m14.8.8l1.402 1.402c1 1 .03 2.7-1.41 2.7H4.21c-1.44 0-2.41-1.7-1.41-2.7L4.2 15.3"
            />
          </svg>
        </div>
        <p className="text-sm font-medium text-gray-700 mb-1">
          Enter a user ID above to see personalized recommendations
        </p>
        <p className="text-xs text-gray-400">
          Try "Known User" for Matrix Factorization or "Cold Start" for the
          popularity fallback
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Panel header */}
      {(hasResults || loading) && (
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold text-gray-900">
            Recommendations
          </h2>
          {modelName && !loading && <ModelBadge modelName={modelName} />}
        </div>
      )}

      {/* Cold-start notice */}
      {modelName === 'popularity' && !loading && (
        <div className="flex items-start gap-2 px-3 py-2.5 bg-amber-50 border border-amber-200 rounded-lg text-sm text-amber-800">
          <svg
            className="w-4 h-4 mt-0.5 flex-shrink-0 text-amber-500"
            fill="currentColor"
            viewBox="0 0 20 20"
          >
            <path
              fillRule="evenodd"
              d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a.75.75 0 000 1.5h.253a.25.25 0 01.244.304l-.459 2.066A1.75 1.75 0 0010.747 15H11a.75.75 0 000-1.5h-.253a.25.25 0 01-.244-.304l.459-2.066A1.75 1.75 0 009.253 9H9z"
              clipRule="evenodd"
            />
          </svg>
          <span>
            This user has no interaction history. Showing globally popular items
            as a fallback.
          </span>
        </div>
      )}

      {/* Loading skeletons */}
      {loading && (
        <div className="space-y-3">
          {Array.from({ length: k }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      )}

      {/* Recommendation cards */}
      {!loading && hasResults && (
        <div className="space-y-3">
          {recommendations.map((rec) => (
            <RecommendationCard
              key={rec.item_id}
              recommendation={rec}
              maxScore={maxScore}
              modelName={modelName as 'mf' | 'popularity'}
            />
          ))}
        </div>
      )}

      {/* No results after a successful request */}
      {!loading && !hasResults && modelName !== null && (
        <div className="bg-white border border-gray-200 rounded-lg py-12 text-center">
          <p className="text-sm text-gray-500">No recommendations returned.</p>
        </div>
      )}
    </div>
  );
}
