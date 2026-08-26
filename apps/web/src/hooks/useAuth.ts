import { useCallback } from 'react';
import { useAuthStore } from '@/stores/authStore';

/** 本地学习者 hook（无登录/注册）。 */
export function useAuth() {
  const user = useAuthStore((s) => s.user);
  const isLoading = useAuthStore((s) => s.isLoading);
  const error = useAuthStore((s) => s.error);
  const fetchMe = useAuthStore((s) => s.fetchMe);
  const clearError = useAuthStore((s) => s.clearError);

  const handleFetchMe = useCallback(() => fetchMe(), [fetchMe]);

  return {
    user,
    isLoading,
    error,
    fetchMe: handleFetchMe,
    clearError,
  };
}
