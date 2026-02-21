/** Loan officer-specific profile form. */

import { useState } from 'react';
import type { LoanOfficerProfile } from '../../types/user';

interface LoanOfficerFormProps {
  data: LoanOfficerProfile;
  onSave: (data: LoanOfficerProfile) => Promise<void>;
  disabled?: boolean;
}

const LOAN_TYPES = ['conventional', 'FHA', 'VA', 'USDA', 'jumbo'];

export function LoanOfficerForm({ data, onSave, disabled }: LoanOfficerFormProps) {
  const [form, setForm] = useState<LoanOfficerProfile>({ ...data });
  const [saving, setSaving] = useState(false);

  const set = (field: keyof LoanOfficerProfile, value: string) =>
    setForm(prev => ({ ...prev, [field]: value }));

  const toggleLoanType = (lt: string) => {
    setForm(prev => ({
      ...prev,
      loan_types_offered: prev.loan_types_offered.includes(lt)
        ? prev.loan_types_offered.filter(t => t !== lt)
        : [...prev.loan_types_offered, lt],
    }));
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await onSave(form);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="role-form">
      <h3>Loan Officer Details</h3>
      <div className="form-grid">
        <label>
          <span>NMLS ID</span>
          <input
            type="text"
            value={form.nmls_id || ''}
            onChange={e => set('nmls_id', e.target.value)}
            placeholder="e.g., 123456"
            disabled={disabled}
          />
        </label>
        <label>
          <span>Company Name</span>
          <input
            type="text"
            value={form.company_name || ''}
            onChange={e => set('company_name', e.target.value)}
            placeholder="Lending company"
            disabled={disabled}
          />
        </label>
        <label>
          <span>Company NMLS</span>
          <input
            type="text"
            value={form.company_nmls || ''}
            onChange={e => set('company_nmls', e.target.value)}
            placeholder="Company NMLS ID"
            disabled={disabled}
          />
        </label>
        <label>
          <span>Contact Preference</span>
          <select
            value={form.contact_preference || ''}
            onChange={e => set('contact_preference', e.target.value)}
            disabled={disabled}
          >
            <option value="">-- Select --</option>
            <option value="email">Email</option>
            <option value="phone">Phone</option>
            <option value="text">Text</option>
          </select>
        </label>
      </div>

      <div className="loan-types-section">
        <span className="form-label">Loan Types Offered</span>
        <div className="loan-type-chips">
          {LOAN_TYPES.map(lt => (
            <button
              key={lt}
              className={`loan-type-chip ${form.loan_types_offered.includes(lt) ? 'loan-type-active' : ''}`}
              onClick={() => toggleLoanType(lt)}
              disabled={disabled}
              type="button"
            >
              {lt}
            </button>
          ))}
        </div>
      </div>

      <button
        className="btn-primary"
        onClick={handleSave}
        disabled={disabled || saving}
      >
        {saving ? 'Saving...' : 'Save Loan Officer Details'}
      </button>
    </div>
  );
}
