/** Connected Services section for the Profile page: Dotloop & DocuSign management. */

import { useEffect, useState } from 'react';
import {
  getDotloopConnectUrl,
  getDocuSignConnectUrl,
  disconnectDotloop,
  disconnectDocuSign,
} from '../../api';

interface IntegrationsSectionProps {
  dotloopConnected: boolean;
  docusignConnected: boolean;
  onRefresh: () => Promise<void>;
}

export function IntegrationsSection({
  dotloopConnected,
  docusignConnected,
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
    if (params.get('docusign_connected') === 'true') {
      setSuccessMessage('DocuSign connected successfully!');
      onRefresh();
      window.history.replaceState({}, '', window.location.pathname);
    }
    if (params.get('dotloop_error')) {
      setErrorMessage(`Dotloop connection failed: ${params.get('dotloop_error')}`);
      window.history.replaceState({}, '', window.location.pathname);
    }
    if (params.get('docusign_error')) {
      setErrorMessage(`DocuSign connection failed: ${params.get('docusign_error')}`);
      window.history.replaceState({}, '', window.location.pathname);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleDisconnect(service: 'dotloop' | 'docusign') {
    setDisconnecting(service);
    setErrorMessage(null);
    setSuccessMessage(null);
    try {
      if (service === 'dotloop') {
        await disconnectDotloop();
      } else {
        await disconnectDocuSign();
      }
      await onRefresh();
      setSuccessMessage(
        `${service === 'dotloop' ? 'Dotloop' : 'DocuSign'} disconnected.`,
      );
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
        Connect your Dotloop and DocuSign accounts to sync document extractions.
      </p>

      {successMessage && (
        <div className="success-banner">{successMessage}</div>
      )}
      {errorMessage && (
        <div className="error-banner">{errorMessage}</div>
      )}

      <div className="integrations-grid">
        {/* Dotloop */}
        <div className={`integration-card ${dotloopConnected ? 'connected' : ''}`}>
          <div className="integration-header">
            <span className="integration-icon">&#x1F517;</span>
            <span className="integration-name">Dotloop</span>
            <span className={`integration-badge ${dotloopConnected ? 'connected' : ''}`}>
              {dotloopConnected ? 'Connected' : 'Ready to Connect'}
            </span>
          </div>
          <p className="integration-description">
            Connect your Dotloop account to sync documents automatically.
          </p>
          {dotloopConnected ? (
            <button
              className="btn-secondary btn-danger"
              onClick={() => handleDisconnect('dotloop')}
              disabled={disconnecting === 'dotloop'}
            >
              {disconnecting === 'dotloop' ? 'Disconnecting...' : 'Disconnect'}
            </button>
          ) : (
            <a href={getDotloopConnectUrl()} className="btn-primary integration-connect-btn">
              Connect Dotloop
            </a>
          )}
        </div>

        {/* DocuSign */}
        <div className={`integration-card ${docusignConnected ? 'connected' : ''}`}>
          <div className="integration-header">
            <span className="integration-icon">&#x1F4DD;</span>
            <span className="integration-name">DocuSign</span>
            <span className={`integration-badge ${docusignConnected ? 'connected' : ''}`}>
              {docusignConnected ? 'Connected' : 'Ready to Connect'}
            </span>
          </div>
          <p className="integration-description">
            Connect your DocuSign account to send envelopes for e-signatures.
          </p>
          {docusignConnected ? (
            <button
              className="btn-secondary btn-danger"
              onClick={() => handleDisconnect('docusign')}
              disabled={disconnecting === 'docusign'}
            >
              {disconnecting === 'docusign' ? 'Disconnecting...' : 'Disconnect'}
            </button>
          ) : (
            <a href={getDocuSignConnectUrl()} className="btn-primary integration-connect-btn">
              Connect DocuSign
            </a>
          )}
        </div>
      </div>
    </section>
  );
}
