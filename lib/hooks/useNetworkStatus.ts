import { useState, useEffect, useCallback } from 'react';
import { processOfflineQueue } from '@/lib/api/client';

interface NetworkStatus {
  isOnline: boolean;
  isChecking: boolean;
  queuedRequests?: number;
}

export function useNetworkStatus(
  onOnline?: () => void,
  onOffline?: () => void,
) {
  const [status, setStatus] = useState<NetworkStatus>({
    isOnline: typeof navigator !== 'undefined' ? navigator.onLine : true,
    isChecking: false,
  });

  const checkConnectivity = useCallback(async () => {
    setStatus(prev => ({ ...prev, isChecking: true }));
    try {
      const response = await fetch('/health/live', {
        method: 'GET',
        cache: 'no-store',
      });
      const isConnected = response.ok;
      setStatus({ isOnline: isConnected, isChecking: false });

      if (isConnected) {
        const { succeeded, failed } = await processOfflineQueue();
        if (succeeded > 0 || failed > 0) {
          if (onOnline) onOnline();
        }
      }

      return isConnected;
    } catch {
      setStatus({ isOnline: false, isChecking: false });
      return false;
    }
  }, [onOnline]);

  useEffect(() => {
    const handleOnline = async () => {
      const isConnected = await checkConnectivity();
      if (isConnected && onOnline) onOnline();
    };

    const handleOffline = () => {
      setStatus(prev => ({ ...prev, isOnline: false }));
      if (onOffline) onOffline();
    };

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, [checkConnectivity, onOnline, onOffline]);

  return { ...status, checkConnectivity };
}
