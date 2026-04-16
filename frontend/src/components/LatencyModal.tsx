import { useEffect } from 'react';
import type { LatencyPoint } from '../types';
import LatencySparkline from './LatencySparkline';

interface LatencyModalProps {
  history: LatencyPoint[];
  onClose: () => void;
}

export default function LatencyModal({ history, onClose }: LatencyModalProps) {
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 sm:p-6"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-xl shadow-xl border border-gray-200 w-full max-w-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
          <div>
            <h2 className="text-sm font-semibold text-gray-900">
              Latency History
            </h2>
            <p className="text-xs text-gray-400 mt-0.5">
              Last {history.length} request{history.length !== 1 ? 's' : ''} ·
              scale is dynamic
            </p>
          </div>
          <button
            onClick={onClose}
            className="flex items-center justify-center w-7 h-7 rounded-md text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
            aria-label="Close"
          >
            <svg
              className="w-4 h-4"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              strokeWidth={2}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </div>

        {/* Expanded chart */}
        <div className="px-5 pt-5 pb-3">
          <LatencySparkline history={history} variant="expanded" />
        </div>

        {/* Explanation */}
        <div className="px-5 pb-5">
          <p className="text-xs text-gray-400 leading-relaxed">
            Cache{' '}
            <span className="font-medium text-gray-600">MISS</span> (large dot)
            appears as a spike — the first request for a given user/k computes
            scores live from the model. Subsequent identical requests hit Redis
            and appear as a flat near-zero line (small dot, cache{' '}
            <span className="font-medium text-gray-600">HIT</span>).
          </p>
        </div>
      </div>
    </div>
  );
}
