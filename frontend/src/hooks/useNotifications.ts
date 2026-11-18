import { useCallback, useState } from 'react';

export interface Notice {
  key: number;
  message: string;
}

let nextKey = 1;

/** Queue of snackbar messages (replaces the WPF WarningSnackbar message queue). */
export function useNotifications() {
  const [queue, setQueue] = useState<Notice[]>([]);
  const notify = useCallback((message: string) => setQueue((q) => [...q, { key: nextKey++, message }]), []);
  const dismiss = useCallback(() => setQueue((q) => q.slice(1)), []);
  return { current: queue[0] ?? null, notify, dismiss };
}
