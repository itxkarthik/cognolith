'use client';

import { useNetworkStatus } from '@/lib/hooks/useNetworkStatus';
import { WifiOff, CheckCircle } from 'lucide-react';
import { useEffect, useState } from 'react';

export function OfflineIndicator() {
  const { isOnline } = useNetworkStatus();
  const [show, setShow] = useState(false);

  useEffect(() => {
    let timeoutId: ReturnType<typeof setTimeout>;
    if (!isOnline) {
      timeoutId = setTimeout(() => setShow(true), 0);
    } else {
      timeoutId = setTimeout(() => setShow(false), 2000);
    }
    return () => clearTimeout(timeoutId);
  }, [isOnline]);

  if (show && !isOnline) {
    return (
      <div className='fixed bottom-4 left-4 right-4 md:right-auto md:w-96 bg-red-50 border border-red-200 rounded-lg p-4 shadow-lg flex items-center gap-3 z-50'>
        <WifiOff className='w-5 h-5 text-red-600 flex-shrink-0' />
        <div>
          <p className='font-semibold text-red-900'>Offline</p>
          <p className='text-sm text-red-700'>Your requests will be queued and synced when online</p>
        </div>
      </div>
    );
  }

  if (isOnline && show) {
    return (
      <div className='fixed bottom-4 left-4 right-4 md:right-auto md:w-96 bg-green-50 border border-green-200 rounded-lg p-4 shadow-lg flex items-center gap-3 z-50 animate-in fade-in duration-200'>
        <CheckCircle className='w-5 h-5 text-green-600 flex-shrink-0' />
        <p className='font-semibold text-green-900'>Back Online</p>
      </div>
    );
  }

  return null;
}
