interface ModelBadgeProps {
  modelName: 'mf' | 'popularity';
}

export default function ModelBadge({ modelName }: ModelBadgeProps) {
  if (modelName === 'mf') {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-blue-50 text-blue-700 border border-blue-200">
        <span className="w-1.5 h-1.5 rounded-full bg-blue-500 inline-block" />
        Personalized · Matrix Factorization
      </span>
    );
  }

  return (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-amber-50 text-amber-700 border border-amber-200">
      <span className="w-1.5 h-1.5 rounded-full bg-amber-500 inline-block" />
      Cold Start · Popularity Fallback
    </span>
  );
}
