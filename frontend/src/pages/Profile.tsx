/** Profile page: personal info, role management, role-specific forms, and AI chat builder. */

import { useState, useEffect } from 'react';
import { Button, Alert, SimpleGrid, TextInput, Group } from '@mantine/core';
import { useProfile } from '../hooks/useProfile';
import { useOnboardingContext } from '../context/OnboardingContext';
import { useClerkAvatar } from '../hooks/useClerkAvatar';
import { useIntegrations } from '../hooks/useIntegrations';
import { RoleSelector } from '../components/profile/RoleSelector';
import { IntegrationsSection } from '../components/profile/IntegrationsSection';
import { AgentForm } from '../components/profile/AgentForm';
import { BuyerForm } from '../components/profile/BuyerForm';
import { SellerForm } from '../components/profile/SellerForm';
import { LoanOfficerForm } from '../components/profile/LoanOfficerForm';
import { CompletionIndicator } from '../components/common/CompletionIndicator';
import { ChatInterface } from '../components/chat/ChatInterface';
import { useChat } from '../hooks/useChat';
import type { AgentProfile, BuyerProfile, SellerProfile, LoanOfficerProfile } from '../types/user';

const DEFAULT_AGENT: AgentProfile = { areas_served: [] };
const DEFAULT_BUYER: BuyerProfile = { pre_approval_status: 'none' };
const DEFAULT_SELLER: SellerProfile = { property_addresses: [] };
const DEFAULT_LO: LoanOfficerProfile = { license_states: [], loan_types_offered: [] };

type ViewMode = 'form' | 'chat';

export function Profile() {
  const {
    profile,
    completion,
    loading,
    error,
    refresh,
    updateSharedFields,
    updateRoleProfile,
    addRole,
    removeRole,
  } = useProfile();

  const { markStepAction } = useOnboardingContext();
  const { avatarUrl } = useClerkAvatar();
  const { dotloopConnected, refresh: refreshIntegrations } = useIntegrations();
  const chatState = useChat();
  const [viewMode, setViewMode] = useState<ViewMode>('form');
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [street, setStreet] = useState('');
  const [city, setCity] = useState('');
  const [state, setState] = useState('');
  const [zip, setZip] = useState('');
  const [sharedSaving, setSharedSaving] = useState(false);

  // Sync form fields whenever profile data changes and we're in form view
  useEffect(() => {
    if (profile && viewMode === 'form' && !loading) {
      setName(profile.name || '');
      setPhone(profile.phone || '');
      setStreet(profile.address?.street || '');
      setCity(profile.address?.city || '');
      setState(profile.address?.state || '');
      setZip(profile.address?.zip || '');
    }
  }, [profile, viewMode, loading]);

  const handleSaveShared = async () => {
    setSharedSaving(true);
    try {
      await updateSharedFields({
        name: name || undefined,
        phone: phone || undefined,
        address: (street || city || state || zip)
          ? { street, city, state, zip }
          : undefined,
      });
      if (name) markStepAction('name_set');
    } finally {
      setSharedSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="page-profile">
        <h1>My Profile</h1>
        <p className="page-subtitle">Loading...</p>
      </div>
    );
  }

  if (error && !profile) {
    return (
      <div className="page-profile">
        <h1>My Profile</h1>
        <p className="page-subtitle">Manage your personal information and roles.</p>
        <div className="placeholder-card">
          <p className="error-text">
            {error.includes('Authentication') || error.includes('401')
              ? 'Connect the backend with MongoDB to enable profile management. Your profile data will be stored securely.'
              : error}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="page-profile">
      <Group justify="space-between" align="flex-start" mb="lg">
        <div>
          <h1>My Profile</h1>
          <p className="page-subtitle">Manage your personal information and roles.</p>
        </div>
        <div className="profile-header-actions">
          {completion && (
            <CompletionIndicator
              percentage={completion.overall}
              label="Profile Completion"
              size="lg"
            />
          )}
          <div className="view-toggle">
            <button
              className={`toggle-btn ${viewMode === 'form' ? 'active' : ''}`}
              onClick={() => { refresh(); setViewMode('form'); }}
            >
              Form View
            </button>
            <button
              className={`toggle-btn ${viewMode === 'chat' ? 'active' : ''}`}
              onClick={() => setViewMode('chat')}
            >
              AI Chat
            </button>
          </div>
        </div>
      </Group>

      {error && <Alert color="red" mb="sm">{error}</Alert>}

      {viewMode === 'chat' ? (
        <ChatInterface chatState={chatState} onProfileUpdated={() => { refresh(); window.dispatchEvent(new Event('profile-updated')); }} />
      ) : (
        <>
          {/* Shared Fields */}
          <section className="profile-section">
            <h2>Personal Information</h2>
            {avatarUrl && (
              <div className="profile-avatar-row">
                <img
                  src={avatarUrl}
                  alt="Profile"
                  className="profile-avatar"
                />
                <span className="profile-avatar-hint">
                  Managed through your login provider
                </span>
              </div>
            )}
            <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm" mb="sm">
              <TextInput
                label="Full Name"
                value={name}
                onChange={e => setName(e.target.value)}
                placeholder="Your full name"
                size="sm"
              />
              <TextInput
                label="Email"
                type="email"
                value={profile?.email || ''}
                disabled
                title="Email is managed through your login provider"
                size="sm"
              />
              <TextInput
                label="Phone"
                type="tel"
                value={phone}
                onChange={e => setPhone(e.target.value)}
                placeholder="(555) 555-5555"
                size="sm"
              />
              <TextInput
                label="Street Address"
                value={street}
                onChange={e => setStreet(e.target.value)}
                placeholder="123 Main St"
                size="sm"
              />
              <TextInput
                label="City"
                value={city}
                onChange={e => setCity(e.target.value)}
                placeholder="City"
                size="sm"
              />
              <TextInput
                label="State"
                value={state}
                onChange={e => setState(e.target.value)}
                placeholder="ST"
                maxLength={2}
                size="sm"
              />
              <TextInput
                label="ZIP Code"
                value={zip}
                onChange={e => setZip(e.target.value)}
                placeholder="12345"
                maxLength={10}
                size="sm"
              />
            </SimpleGrid>
            <Button
              variant="filled"
              color="cyan"
              onClick={handleSaveShared}
              disabled={sharedSaving}
            >
              {sharedSaving ? 'Saving...' : 'Save Personal Info'}
            </Button>
          </section>

          {/* Connected Services */}
          <IntegrationsSection
            dotloopConnected={dotloopConnected}
            onRefresh={refreshIntegrations}
          />

          {/* Role Management */}
          <section className="profile-section">
            <RoleSelector
              currentRoles={profile?.user_types || []}
              onAddRole={(role) => { addRole(role); markStepAction('role_selected'); }}
              onRemoveRole={removeRole}
            />
          </section>

          {/* Role-Specific Forms */}
          {profile?.user_types.includes('agent') && (
            <section className="profile-section">
              {completion?.roles.agent !== undefined && (
                <CompletionIndicator percentage={completion.roles.agent} label="Agent" size="sm" />
              )}
              <AgentForm
                data={profile.agent_profile || DEFAULT_AGENT}
                onSave={(data) => updateRoleProfile('agent', data)}
              />
            </section>
          )}

          {profile?.user_types.includes('buyer') && (
            <section className="profile-section">
              {completion?.roles.buyer !== undefined && (
                <CompletionIndicator percentage={completion.roles.buyer} label="Buyer" size="sm" />
              )}
              <BuyerForm
                data={profile.buyer_profile || DEFAULT_BUYER}
                onSave={(data) => updateRoleProfile('buyer', data)}
              />
            </section>
          )}

          {profile?.user_types.includes('seller') && (
            <section className="profile-section">
              {completion?.roles.seller !== undefined && (
                <CompletionIndicator percentage={completion.roles.seller} label="Seller" size="sm" />
              )}
              <SellerForm
                data={profile.seller_profile || DEFAULT_SELLER}
                onSave={(data) => updateRoleProfile('seller', data)}
              />
            </section>
          )}

          {profile?.user_types.includes('loan_officer') && (
            <section className="profile-section">
              {completion?.roles.loan_officer !== undefined && (
                <CompletionIndicator percentage={completion.roles.loan_officer} label="Loan Officer" size="sm" />
              )}
              <LoanOfficerForm
                data={profile.loan_officer_profile || DEFAULT_LO}
                onSave={(data) => updateRoleProfile('loan_officer', data)}
              />
            </section>
          )}

          {/* Prompt to add a role if none selected */}
          {profile && profile.user_types.length === 0 && (
            <div className="placeholder-card">
              <p>Select at least one role above to unlock role-specific profile fields.</p>
            </div>
          )}
        </>
      )}
    </div>
  );
}
