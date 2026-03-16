/** Hook for managing integration connection status (Dotloop). */

import { useState, useEffect, useCallback } from 'react';
import { checkDotloopStatus } from '../api';

export interface UseIntegrationsReturn {
  dotloopConnected: boolean;
  loading: boolean;
  /** Re-check integration status from the backend. */
  refresh: () => Promise<void>;
}

export function useIntegrations(): UseIntegrationsReturn {
  const [dotloopConnected, setDotloopConnected] = useState(false);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const dl = await checkDotloopStatus();
      setDotloopConnected(dl);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { dotloopConnected, loading, refresh };
}
