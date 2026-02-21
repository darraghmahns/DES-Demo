/** Dashboard with profile completion prompts and quick-access cards. */

import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { CompletionIndicator } from '../components/common/CompletionIndicator';
import type { ProfileCompletion } from '../api/profile';
import { getProfileCompletion } from '../api/profile';

export function Dashboard() {
  const [completion, setCompletion] = useState<ProfileCompletion | null>(null);

  useEffect(() => {
    getProfileCompletion()
      .then(setCompletion)
      .catch(() => { /* Backend not available — no-op */ });
  }, []);

  const missingCount = completion
    ? Object.values(completion.missing_fields).flat().length
    : 0;

  return (
    <div className="page-dashboard">
      <h1>Dashboard</h1>
      <p className="page-subtitle">Welcome to D.E.S. — Data Entry Sucks</p>

      {/* Profile Completion Banner */}
      {completion && completion.overall < 100 && (
        <div className="dashboard-completion-banner">
          <CompletionIndicator percentage={completion.overall} label="Profile" size="md" />
          <div className="completion-banner-text">
            <p>
              Your profile is {Math.round(completion.overall)}% complete.
              {missingCount > 0 && ` ${missingCount} field${missingCount > 1 ? 's' : ''} remaining.`}
            </p>
            <Link to="/profile" className="btn-link">Complete Profile</Link>
          </div>
        </div>
      )}

      <div className="dashboard-grid">
        <Link to="/extraction" className="dashboard-card">
          <div className="dashboard-card-icon">&#x229C;</div>
          <h3>Document Extraction</h3>
          <p>Upload and extract data from real estate documents using AI.</p>
        </Link>

        <Link to="/transactions" className="dashboard-card">
          <div className="dashboard-card-icon">&#x22A1;</div>
          <h3>Transactions</h3>
          <p>Manage deals, invite participants, and track document requirements.</p>
        </Link>

        <Link to="/profile" className="dashboard-card">
          <div className="dashboard-card-icon">&#x2299;</div>
          <h3>My Profile</h3>
          <p>Complete your profile and manage your roles.</p>
          {completion && completion.overall < 100 && (
            <div className="card-completion">
              <CompletionIndicator percentage={completion.overall} size="sm" />
            </div>
          )}
        </Link>

        <Link to="/profile/documents" className="dashboard-card">
          <div className="dashboard-card-icon">&#x229F;</div>
          <h3>My Documents</h3>
          <p>Upload financials, bank statements, and other required documents.</p>
        </Link>
      </div>
    </div>
  );
}
