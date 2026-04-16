export default function SkeletonCard() {
  return (
    <div className="bg-white border border-gray-200 rounded-lg p-4">
      <div className="flex items-start gap-3">
        {/* Rank badge placeholder */}
        <div className="skeleton-shimmer w-8 h-8 rounded-full flex-shrink-0" />

        <div className="flex-1 min-w-0 space-y-2">
          {/* Item ID line */}
          <div className="skeleton-shimmer h-4 w-24 rounded" />
          {/* Product name line */}
          <div className="skeleton-shimmer h-3 w-40 rounded" />
          {/* Category line */}
          <div className="skeleton-shimmer h-3 w-20 rounded" />
          {/* Score bar */}
          <div className="skeleton-shimmer h-1.5 w-full rounded-full mt-3" />
        </div>

        {/* Score placeholder */}
        <div className="skeleton-shimmer h-4 w-16 rounded flex-shrink-0" />
      </div>
    </div>
  );
}
