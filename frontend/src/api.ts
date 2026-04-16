import type { ApiResponse } from './types';
import { ApiError } from './types';

async function fetchWithTimeout(
  url: string,
  timeoutMs: number,
): Promise<Response> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, { signal: controller.signal });
    clearTimeout(timeoutId);
    return response;
  } catch (err) {
    clearTimeout(timeoutId);
    if (err instanceof Error && err.name === 'AbortError') {
      throw new Error('timeout');
    }
    throw err;
  }
}

export async function fetchRecommendationsApi(
  userId: string,
  k: number,
): Promise<ApiResponse> {
  const params = new URLSearchParams({
    user_id: userId,
    k: String(k),
  });

  const response = await fetchWithTimeout(
    `/api/recommendations?${params}`,
    5000,
  );

  if (!response.ok) {
    throw new ApiError(response.status, await response.text());
  }

  const data: unknown = await response.json();

  // Defensive: validate shape
  if (
    typeof data !== 'object' ||
    data === null ||
    !Array.isArray((data as ApiResponse).recommendations)
  ) {
    throw new Error('Unexpected response shape from server.');
  }

  return data as ApiResponse;
}

export async function checkHealthApi(): Promise<boolean> {
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 3000);
    const response = await fetch('/api/health', {
      signal: controller.signal,
    });
    clearTimeout(timeoutId);
    return response.ok;
  } catch {
    return false;
  }
}
