import { create } from 'zustand';
import { fetchRecommendationsApi, checkHealthApi } from './api';
import type { Recommendation, HistoryEntry, ErrorType } from './types';
import { ApiError } from './types';

const MAX_HISTORY = 5;

interface StoreState {
  // Inputs
  userId: string;
  k: number;

  // API response data
  recommendations: Recommendation[];
  modelName: 'mf' | 'popularity' | null;
  latencyMs: number | null;
  servedFromCache: boolean | null;
  itemsReturned: number | null;

  // UI state
  loading: boolean;
  error: string | null;
  errorType: ErrorType;
  isHealthy: boolean;

  // History
  requestHistory: HistoryEntry[];

  // Actions
  setUserId: (id: string) => void;
  setK: (k: number) => void;
  fetchRecommendations: () => Promise<void>;
  checkHealth: () => Promise<void>;
}

export const useStore = create<StoreState>((set, get) => ({
  userId: '',
  k: 10,
  recommendations: [],
  modelName: null,
  latencyMs: null,
  servedFromCache: null,
  itemsReturned: null,
  loading: false,
  error: null,
  errorType: null,
  isHealthy: false,
  requestHistory: [],

  setUserId: (id) => set({ userId: id }),
  setK: (k) => set({ k }),

  fetchRecommendations: async () => {
    const { userId, k } = get();

    if (!userId.trim()) {
      set({ error: 'Please enter a user ID.', errorType: '422' });
      return;
    }

    set({ loading: true, error: null, errorType: null });

    try {
      const data = await fetchRecommendationsApi(userId.trim(), k);

      const entry: HistoryEntry = {
        userId: userId.trim(),
        modelName: data.model_name,
        latencyMs: data.latency_ms,
        cached: data.served_from_cache,
        timestamp: Date.now(),
      };

      set((state) => ({
        recommendations: data.recommendations,
        modelName: data.model_name,
        latencyMs: data.latency_ms,
        servedFromCache: data.served_from_cache,
        itemsReturned: data.recommendations.length,
        loading: false,
        error: null,
        errorType: null,
        requestHistory: [
          entry,
          ...state.requestHistory.slice(0, MAX_HISTORY - 1),
        ],
      }));
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 422) {
          set({
            loading: false,
            error: 'Invalid user ID. Please check the format and try again.',
            errorType: '422',
          });
        } else if (err.status === 503) {
          set({
            loading: false,
            error:
              'Models not loaded — run training and restart the inference service.',
            errorType: '503',
          });
        } else {
          set({
            loading: false,
            error: `Server error (${err.status}). Please try again.`,
            errorType: 'network',
          });
        }
      } else if (err instanceof Error && err.message === 'timeout') {
        set({
          loading: false,
          error: 'Request timed out. The backend may be under load.',
          errorType: 'timeout',
        });
      } else {
        set({
          loading: false,
          error:
            'Cannot connect to backend. Is the inference service running on port 8002?',
          errorType: 'network',
        });
      }
    }
  },

  checkHealth: async () => {
    const healthy = await checkHealthApi();
    set({ isHealthy: healthy });
  },
}));
