'use client';

import { useNetworkStatus } from '@/lib/hooks/useNetworkStatus';
import { requestQueue } from '@/lib/utils/requestQueue';
import { useState, useEffect } from 'react';
import { motion } from 'motion/react';

import { Badge, Card, CardContent, CardDescription, CardHeader, CardTitle, Separator } from '@/components/ui';

export function StatusTerminal() {
  const { isOnline } = useNetworkStatus();
  const [queueCount, setQueueCount] = useState(() => requestQueue.size());
  const [latency, setLatency] = useState(0);

  useEffect(() => {
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
    <motion.div
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.35, ease: 'easeOut' }}
      className='fixed right-8 top-20 z-20'
    >
    <Card className='w-[18rem] border-cyan-500/25 bg-[#070b1d]/90 shadow-2xl backdrop-blur-xl'>
      <CardHeader className='space-y-2 px-4 py-4'>
        <div className='flex items-center justify-between'>
          <CardTitle className='text-sm font-semibold tracking-wide text-white'>System Status</CardTitle>
          <Badge variant={isOnline ? 'secondary' : 'destructive'} className='rounded-full px-2.5 py-0.5 text-[10px] uppercase tracking-[0.18em]'>
            {status}
          </Badge>
        </div>
        <CardDescription className='text-xs text-white/55'>Realtime connectivity and queue health.</CardDescription>
      </CardHeader>
      <CardContent className='px-4 pb-4'>
        <div className='flex items-center gap-3'>
          <div className={'h-2.5 w-2.5 rounded-full ' + dotColor + ' ' + pulseClass}></div>
          <div className='font-mono text-[10px] tracking-[0.2em] text-white/80'>ETHER_OS</div>
        </div>
        <Separator className='my-3 bg-white/8' />
        <div className='space-y-1 font-mono text-[11px] leading-5 tracking-tight text-white/75'>
          <div className={statusColor}>STATUS // {status}</div>
          <div className='text-[#bcff5f]'>LATENCY // {latency}ms</div>
          <div className='text-white/60'>{syncStatus}</div>
        </div>
      </CardContent>
    </Card>
    </motion.div>
  );
}
