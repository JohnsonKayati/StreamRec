import { useStore } from '../store';

export default function ErrorBanner() {
  const error = useStore((s) => s.error);
  const errorType = useStore((s) => s.errorType);

  // 422 is shown inline in ControlBar, not as a banner
  if (!error || errorType === '422') return null;

  const is503 = errorType === '503';

  const containerClass = is503
    ? 'bg-amber-50 border-amber-200 text-amber-800'
    : 'bg-red-50 border-red-200 text-red-800';

  const iconClass = is503 ? 'text-amber-500' : 'text-red-500';

  return (
    <div className={`border rounded-lg px-4 py-3 flex items-start gap-3 ${containerClass}`}>
      <svg
        className={`w-4 h-4 mt-0.5 flex-shrink-0 ${iconClass}`}
        fill="currentColor"
        viewBox="0 0 20 20"
      >
        {is503 ? (
          <path
            fillRule="evenodd"
            d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 5a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 5zm0 9a1 1 0 100-2 1 1 0 000 2z"
            clipRule="evenodd"
          />
        ) : (
          <path
            fillRule="evenodd"
            d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z"
            clipRule="evenodd"
          />
        )}
      </svg>
      <span className="text-sm">{error}</span>
    </div>
  );
}
