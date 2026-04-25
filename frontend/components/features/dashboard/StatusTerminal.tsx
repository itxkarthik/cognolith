'use client';

import { useNetworkStatus } from '@/lib/hooks/useNetworkStatus';
import { requestQueue } from '@/lib/utils/requestQueue';
import { useState, useEffect } from 'react';

export function StatusTerminal() {
  const { isOnline } = useNetworkStatus();
  const [queueCount, setQueueCount] = useState(0);
  const [latency, setLatency] = useState(0);

  useEffect(() => {
    setQueueCount(requestQueue.size());
    const interval = setInterval(() => setQueueCount(requestQueue.size()), 1000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const start = performance.now();
    fetch('/health/live', { method: 'GET', cache: 'no-store' })
      .then(() => setLatency(Math.round(performance.now() - start)))
      .catch(() => setLatency(-1));
  }, []);

  const status = isOnline ? 'ONLINE' : 'OFFLINE';
  const statusColor = isOnline ? 'text-[#bcff5f]' : 'text-[#ff6b6b]';
  const dotColor = isOnline ? 'bg-[#bcff5f]' : 'bg-[#ff6b6b]';
  const pulseClass = isOnline ? 'animate-pulse' : 'animate-bounce';
  const syncStatus = queueCount > 0 ? 'SYNC: ' + queueCount + ' PENDING' : 'SYNC: 100%';

  return (
    <div className='fixed top-20 right-8 z-20 glass-panel border border-[#464554]/20 rounded-lg p-3 ambient-glow'>
      <div className='flex items-center gap-3'>
        <div className={'w-2 h-2 rounded-full ' + dotColor + ' ' + pulseClass}></div>
        <div className='font-mono text-[10px] tracking-tighter'>
          <div className={statusColor}>ETHER_OS :: {status}</div>
          <div className='text-[#bcff5f]'>LATENCY: {latency}ms // {syncStatus}</div>
        </div>
      </div>
    </div>
  );
}
