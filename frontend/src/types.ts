export interface Recommendation {
  item_id: string;
  score: number;
  rank: number;
}

export interface ApiResponse {
  user_id: string;
  recommendations: Recommendation[];
  model_name: 'mf' | 'popularity';
  served_from_cache: boolean;
  latency_ms: number;
}

export interface HistoryEntry {
  userId: string;
  modelName: string;
  latencyMs: number;
  cached: boolean;
  timestamp: number;
}

/** One data point for the latency sparkline — newest-first in the store array. */
export interface LatencyPoint {
  latencyMs: number;
  cached: boolean;
  timestamp: number;
}

export type ErrorType = 'network' | '503' | '422' | 'timeout' | null;

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

