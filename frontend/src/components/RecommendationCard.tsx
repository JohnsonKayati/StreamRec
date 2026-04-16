import { getFakeMetadata } from '../lib/fake-metadata';
import type { Recommendation } from '../types';

interface RecommendationCardProps {
  recommendation: Recommendation;
  maxScore: number;
  modelName: 'mf' | 'popularity';
  isNew?: boolean;
}

export default function RecommendationCard({
  recommendation,
  maxScore,
  modelName,
  isNew = false,
}: RecommendationCardProps) {
  const { item_id, score, rank } = recommendation;
  const { name, category } = getFakeMetadata(item_id);

  const scorePercent = maxScore > 0 ? (score / maxScore) * 100 : 0;
  const isMf = modelName === 'mf';

  const leftBorderClass = isMf ? 'border-l-blue-400' : 'border-l-amber-400';
  const rankBgClass = isMf
    ? 'bg-blue-50 text-blue-700'
    : 'bg-amber-50 text-amber-700';
  const scoreBarClass = isMf ? 'bg-blue-400' : 'bg-amber-400';
  const newBorderClass = isNew ? 'ring-1 ring-green-300' : '';

  return (
    <div
      className={`bg-white border border-gray-200 border-l-4 ${leftBorderClass} rounded-lg p-4 ${newBorderClass}`}
    >
      <div className="flex items-start gap-3">
        {/* Rank badge */}
        <div
          className={`w-8 h-8 rounded-full flex-shrink-0 flex items-center justify-center text-xs font-semibold ${rankBgClass}`}
        >
          #{rank}
        </div>

        <div className="flex-1 min-w-0">
          {/* Item ID + popularity badge */}
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-mono text-sm font-medium text-gray-900">
              {item_id}
            </span>
            {!isMf && (
              <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-amber-50 text-amber-600 border border-amber-200">
                Popular
              </span>
            )}
            {isNew && (
              <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-green-50 text-green-600 border border-green-200">
                New
              </span>
            )}
          </div>

          {/* Fake product name */}
          <div className="text-sm text-gray-700 mt-0.5 truncate">{name}</div>

          {/* Category */}
          <div className="text-xs text-gray-400 mt-0.5">{category}</div>

          {/* Score bar */}
          <div className="mt-2.5 h-1.5 bg-gray-100 rounded-full overflow-hidden">
            <div
              className={`h-full ${scoreBarClass} rounded-full score-bar-fill`}
              style={{ width: `${scorePercent}%` }}
            />
          </div>
        </div>

        {/* Score value */}
        <div className="flex-shrink-0 text-right">
          <span className="font-mono text-xs text-gray-500">
            {score.toFixed(4)}
          </span>
        </div>
      </div>
    </div>
  );
}
