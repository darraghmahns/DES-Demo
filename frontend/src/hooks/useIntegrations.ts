/** Hook for managing integration connection status (Dotloop, DocuSign). */

import { useState, useEffect, useCallback } from 'react';
import { checkDotloopStatus, checkDocuSignStatus } from '../api';

export interface UseIntegrationsReturn {
  dotloopConnected: boolean;
  docusignConnected: boolean;
  loading: boolean;
  /** Re-check integration status from the backend. */
  refresh: () => Promise<void>;
}

export function useIntegrations(): UseIntegrationsReturn {
  const [dotloopConnected, setDotloopConnected] = useState(false);
  const [docusignConnected, setDocusignConnected] = useState(false);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [dl, ds] = await Promise.all([
        checkDotloopStatus(),
        checkDocuSignStatus(),
      ]);
      setDotloopConnected(dl);
      setDocusignConnected(ds);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { dotloopConnected, docusignConnected, loading, refresh };
}
