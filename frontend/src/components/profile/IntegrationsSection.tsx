/** Connected Services section for the Profile page: Dotloop management. */

import { useEffect, useState } from 'react';
import { Button, Alert, SimpleGrid, Card } from '@mantine/core';
import {
  getDotloopConnectUrl,
  disconnectDotloop,
} from '../../api';

interface IntegrationsSectionProps {
  dotloopConnected: boolean;
  onRefresh: () => Promise<void>;
}

export function IntegrationsSection({
  dotloopConnected,
  onRefresh,
}: IntegrationsSectionProps) {
  const [disconnecting, setDisconnecting] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Handle OAuth redirect query params (after connect callback)
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);

    if (params.get('dotloop_connected') === 'true') {
      setSuccessMessage('Dotloop connected successfully!');
      onRefresh();
      window.history.replaceState({}, '', window.location.pathname);
    }
    if (params.get('dotloop_error')) {
      setErrorMessage(`Dotloop connection failed: ${params.get('dotloop_error')}`);
      window.history.replaceState({}, '', window.location.pathname);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleDisconnect() {
    setDisconnecting('dotloop');
    setErrorMessage(null);
    setSuccessMessage(null);
    try {
      await disconnectDotloop();
      await onRefresh();
      setSuccessMessage('Dotloop disconnected.');
    } catch (e) {
      setErrorMessage(e instanceof Error ? e.message : 'Disconnect failed');
    } finally {
      setDisconnecting(null);
    }
  }

  return (
    <section className="profile-section">
      <h2>Connected Services</h2>
      <p className="page-subtitle" style={{ marginBottom: 16 }}>
        Connect your Dotloop account to sync document extractions.
      </p>

      {successMessage && (
        <Alert color="green" mb="sm">{successMessage}</Alert>
      )}
      {errorMessage && (
        <Alert color="red" mb="sm">{errorMessage}</Alert>
      )}

      <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md">
        {/* Dotloop */}
        <Card withBorder padding="md" className={dotloopConnected ? 'connected' : undefined}>
          <div className="integration-header">
            <span className="integration-icon">DL</span>
            <span className="integration-name">Dotloop</span>
            <span className={`integration-badge ${dotloopConnected ? 'connected' : ''}`}>
              {dotloopConnected ? 'Connected' : 'Ready to Connect'}
            </span>
          </div>
          <p className="integration-description">
            Connect your Dotloop account to sync documents automatically.
          </p>
          {dotloopConnected ? (
            <Button
              variant="outline"
              color="red"
              onClick={() => handleDisconnect()}
              disabled={disconnecting === 'dotloop'}
            >
              {disconnecting === 'dotloop' ? 'Disconnecting...' : 'Disconnect'}
            </Button>
          ) : (
            <Button component="a" href={getDotloopConnectUrl()} variant="filled" color="cyan">
              Connect Dotloop
            </Button>
          )}
        </Card>
      </SimpleGrid>
    </section>
  );
}
