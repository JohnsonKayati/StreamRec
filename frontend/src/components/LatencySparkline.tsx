import type { LatencyPoint } from '../types';

interface LatencySparklineProps {
  history: LatencyPoint[];
  variant?: 'compact' | 'expanded';
}

const THRESHOLD_GREEN = 5;
const THRESHOLD_YELLOW = 20;

// Minimum visible range (ms). If all values are within 0.5ms of each other,
// artificially widen the window so the line never goes flat.
const MIN_RANGE = 0.5;

const VARIANTS = {
  compact: {
    W: 220, H: 64,
    pad: { top: 12, bottom: 12, left: 6, right: 6 },
    fontSize: 9,
    svgClass: 'w-full h-16',
    dotR: { hit: 3, miss: 4 },
  },
  expanded: {
    W: 500, H: 120,
    pad: { top: 16, bottom: 16, left: 6, right: 6 },
    fontSize: 10,
    svgClass: 'w-full h-[120px]',
    dotR: { hit: 3.5, miss: 5.5 },
  },
} as const;

function dotColor(ms: number): string {
  if (ms < THRESHOLD_GREEN) return '#22c55e';
  if (ms < THRESHOLD_YELLOW) return '#eab308';
  return '#ef4444';
}

function dotColorClass(ms: number): string {
  if (ms < THRESHOLD_GREEN) return 'text-green-500';
  if (ms < THRESHOLD_YELLOW) return 'text-yellow-500';
  return 'text-red-500';
}

export { dotColorClass };

/**
 * Compute a zoomed Y-axis window from actual data so tiny differences fill
 * the full chart height rather than collapsing to a flat line.
 *
 * Algorithm:
 *   raw range  = max - min (clamped to MIN_RANGE)
 *   padding    = range * 0.3  (30% breathing room on each side)
 *   yMin       = max(0, min - padding)   -- never go below zero
 *   yMax       = max + padding
 */
function computeYWindow(values: number[]): { yMin: number; yMax: number } {
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const range = Math.max(hi - lo, MIN_RANGE);
  const pad = range * 0.3;
  return {
    yMin: Math.max(0, lo - pad),
    yMax: hi + pad,
  };
}

export default function LatencySparkline({
  history,
  variant = 'compact',
}: LatencySparklineProps) {
  const { W, H, pad, fontSize, svgClass, dotR } = VARIANTS[variant];
  const INNER_W = W - pad.left - pad.right;
  const INNER_H = H - pad.top - pad.bottom;

  const points = [...history].reverse();

  if (points.length === 0) {
    return (
      <div
        className={`flex items-center justify-center ${svgClass} text-xs text-gray-400 italic`}
      >
        No data yet — make a request
      </div>
    );
  }

  const { yMin, yMax } = computeYWindow(points.map((p) => p.latencyMs));
  const ySpan = yMax - yMin;

  const toX = (i: number): number => {
    if (points.length === 1) return pad.left + INNER_W / 2;
    return pad.left + (i / (points.length - 1)) * INNER_W;
  };

  // Map actual ms value into the zoomed window
  const toY = (ms: number): number =>
    pad.top + INNER_H - ((ms - yMin) / ySpan) * INNER_H;

  // Threshold line at 5ms — only draw if it falls inside the visible window
  const yGreenLine = toY(THRESHOLD_GREEN);
  const showThreshold =
    THRESHOLD_GREEN >= yMin &&
    THRESHOLD_GREEN <= yMax &&
    yGreenLine > pad.top &&
    yGreenLine < H - pad.bottom;

  const linePoints = points
    .map((p, i) => `${toX(i)},${toY(p.latencyMs)}`)
    .join(' ');

  const firstX = toX(0);
  const lastX = toX(points.length - 1);
  const bottomY = H - pad.bottom;
  const areaPath = `M ${firstX},${toY(points[0].latencyMs)} ${points
    .slice(1)
    .map((p, i) => `L ${toX(i + 1)},${toY(p.latencyMs)}`)
    .join(' ')} L ${lastX},${bottomY} L ${firstX},${bottomY} Z`;

  const latestPoint = points[points.length - 1];
  const gradId = `sparkFill-${variant}`;

  return (
    <div>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className={svgClass}
        aria-label="Latency sparkline (zoomed)"
      >
        <defs>
          <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#6366f1" stopOpacity="0.15" />
            <stop offset="100%" stopColor="#6366f1" stopOpacity="0" />
          </linearGradient>
        </defs>

        {showThreshold && (
          <line
            x1={pad.left}
            y1={yGreenLine}
            x2={W - pad.right}
            y2={yGreenLine}
            stroke="#d1fae5"
            strokeWidth="1"
            strokeDasharray="3 3"
          />
        )}

        <path d={areaPath} fill={`url(#${gradId})`} />

        <polyline
          points={linePoints}
          fill="none"
          stroke="#94a3b8"
          strokeWidth="1.5"
          strokeLinejoin="round"
          strokeLinecap="round"
        />

        {points.map((p, i) => (
          <circle
            key={p.timestamp}
            cx={toX(i)}
            cy={toY(p.latencyMs)}
            r={p.cached ? dotR.hit : dotR.miss}
            fill={dotColor(p.latencyMs)}
            stroke="white"
            strokeWidth="1"
          />
        ))}

        {latestPoint && (
          <text
            x={W - pad.right}
            y={pad.top - 2}
            textAnchor="end"
            fontSize={fontSize}
            fill="#94a3b8"
            fontFamily="monospace"
          >
            latest: {latestPoint.latencyMs.toFixed(2)}ms
          </text>
        )}
      </svg>

      {/* Legend */}
      <div className="flex items-center gap-3 mt-1">
        <div className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-green-500 inline-block" />
          <span className="text-xs text-gray-400">&lt;5ms</span>
        </div>
        <div className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-yellow-500 inline-block" />
          <span className="text-xs text-gray-400">5–20ms</span>
        </div>
        <div className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-red-500 inline-block" />
          <span className="text-xs text-gray-400">&gt;20ms</span>
        </div>
        <div className="flex items-center gap-1 ml-auto">
          <span className="text-xs text-gray-400">large dot = MISS</span>
        </div>
      </div>
      <p className="mt-1 text-xs text-gray-400 italic">
        Zoomed view (relative scale)
      </p>
    </div>
  );
}
