import { useParams } from 'react-router-dom';

export function InviteLanding() {
  const { token } = useParams<{ token: string }>();

  return (
    <div className="page-invite">
      <h1>You've Been Invited</h1>
      <p className="page-subtitle">Complete your profile to join this transaction.</p>

      <div className="placeholder-card">
        <p>Magic link onboarding coming in Phase 3.</p>
        <p>Token: {token ? `${token.slice(0, 12)}...` : 'none'}</p>
        <p>This page will guide you through:</p>
        <ul>
          <li>Profile completion (personal info + role details)</li>
          <li>Document uploads (required for the transaction)</li>
          <li>Clerk account creation (for persistent access)</li>
        </ul>
      </div>
    </div>
  );
}
