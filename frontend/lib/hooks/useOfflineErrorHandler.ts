import { useCallback } from 'react';
import { toast } from 'sonner';
import { APIRequestError } from '@/lib/api/client';

export function useOfflineErrorHandler() {
  const handleError = useCallback((error: unknown) => {
    if (error instanceof APIRequestError) {
      if (error.errorCode === 'OFFLINE') {
        toast.info('Request queued. Will sync when you are online.');
        return true;
      }

      if (error.statusCode === 0 || error.message.includes('offline')) {
        toast.error('Unable to reach the server. Please check your connection.');
        return true;
      }
    }

    return false;
  }, []);

  return { handleError };
}
