import { api, ApiError } from "./api";

const KEY = "homematch_session_id";

export async function getOrCreateSessionId(): Promise<string> {
  const existing = localStorage.getItem(KEY);
  if (existing) return existing;
  const { session_id } = await api.createSession();
  localStorage.setItem(KEY, session_id);
  return session_id;
}

export function resetSession(): void {
  localStorage.removeItem(KEY);
}

/**
 * Chạy `fn(sessionId)`; nếu backend trả 404 (session_id cũ trỏ vào DB đã bị seed lại —
 * hay gặp khi dev reseed `data/app.db` mà không xoá localStorage), tạo phiên mới và
 * thử lại đúng 1 lần.
 */
export async function withSession<T>(fn: (sessionId: string) => Promise<T>): Promise<T> {
  const sessionId = await getOrCreateSessionId();
  try {
    return await fn(sessionId);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) {
      resetSession();
      const freshId = await getOrCreateSessionId();
      return await fn(freshId);
    }
    throw e;
  }
}
