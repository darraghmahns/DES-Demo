/** Magic link landing page — validate invitation, accept, and complete profile. */

import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { Button } from '@mantine/core';
import { ComparariLogo } from '../components/branding/ComparariLogo';
import {
  validateInvitation,
  acceptInvitation,
  submitProfileViaMagicLink,
  type InvitationValidation,
} from '../api/transactions';

type Step = 'loading' | 'welcome' | 'profile' | 'done' | 'error';

const ROLE_LABELS: Record<string, string> = {
  BUYER: 'Buyer',
  SELLER: 'Seller',
  LISTING_AGENT: 'Listing Agent',
  BUYING_AGENT: 'Buying Agent',
  LOAN_OFFICER: 'Loan Officer',
  ESCROW_TITLE_REP: 'Escrow/Title Rep',
  OTHER: 'Participant',
};

export function InviteLanding() {
  const { token } = useParams<{ token: string }>();
  const [step, setStep] = useState<Step>('loading');
  const [invitation, setInvitation] = useState<InvitationValidation | null>(null);
  const [errorMsg, setErrorMsg] = useState('');
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!token) {
      setErrorMsg('No invitation token provided.');
      setStep('error');
      return;
    }

    validateInvitation(token)
      .then(data => {
        setInvitation(data);
        setName(data.name || '');
        setStep('welcome');
      })
      .catch(err => {
        setErrorMsg(err instanceof Error ? err.message : 'Invalid or expired invitation.');
        setStep('error');
      });
  }, [token]);

  const handleAccept = async () => {
    if (!token) return;
    try {
      await acceptInvitation(token);
      setStep('profile');
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to accept invitation.');
      setStep('error');
    }
  };

  const handleProfileSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) return;
    setSubmitting(true);
    try {
      await submitProfileViaMagicLink(token, {
        name: name.trim() || undefined,
        phone: phone.trim() || undefined,
      });
      setStep('done');
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to save profile.');
      setStep('error');
    }
    setSubmitting(false);
  };

  return (
    <div className="page-invite">
      <div className="invite-container">
        <ComparariLogo className="invite-logo-lockup" wordmarkClassName="invite-logo" />

        {step === 'loading' && (
          <div className="invite-card">
            <p>Validating your invitation...</p>
          </div>
        )}

        {step === 'error' && (
          <div className="invite-card invite-error">
            <h2>Something went wrong</h2>
            <p>{errorMsg}</p>
            <p>This link may have expired or already been used.</p>
          </div>
        )}

        {step === 'welcome' && invitation && (
          <div className="invite-card">
            <h2>You've Been Invited</h2>
            {invitation.transaction && (
              <>
                <p className="invite-txn-name">
                  Transaction: <strong>{invitation.transaction.name}</strong>
                </p>
                <p className="invite-role">
                  Role: <strong>{ROLE_LABELS[invitation.transaction.role || ''] || invitation.transaction.role}</strong>
                </p>
              </>
            )}
            <p>
              You're invited to join as a participant. Accept to continue and complete your profile.
            </p>
            <Button variant="filled" color="campari" onClick={handleAccept}>
              Accept Invitation
            </Button>
          </div>
        )}

        {step === 'profile' && (
          <div className="invite-card">
            <h2>Complete Your Profile</h2>
            <p>Please provide your details to participate in this transaction.</p>
            <form className="invite-profile-form" onSubmit={handleProfileSubmit}>
              <div className="form-field">
                <label>Full Name</label>
                <input
                  type="text"
                  value={name}
                  onChange={e => setName(e.target.value)}
                  placeholder="Your full legal name"
                  required
                />
              </div>
              <div className="form-field">
                <label>Phone Number</label>
                <input
                  type="tel"
                  value={phone}
                  onChange={e => setPhone(e.target.value)}
                  placeholder="(555) 123-4567"
                />
              </div>
              <Button type="submit" variant="filled" color="campari" disabled={submitting}>
                {submitting ? 'Saving...' : 'Save & Continue'}
              </Button>
            </form>
          </div>
        )}

        {step === 'done' && (
          <div className="invite-card invite-success">
            <h2>You're All Set!</h2>
            <p>Your profile has been saved and you've been added to the transaction.</p>
            <p>
              For ongoing access, <Link to="/login">create a full account</Link>.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
