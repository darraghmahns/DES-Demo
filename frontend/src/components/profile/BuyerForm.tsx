/** Buyer-specific profile form. */

import { useState } from 'react';
import type { BuyerProfile, PreApprovalStatus } from '../../types/user';

interface BuyerFormProps {
  data: BuyerProfile;
  onSave: (data: BuyerProfile) => Promise<void>;
  disabled?: boolean;
}

export function BuyerForm({ data, onSave, disabled }: BuyerFormProps) {
  const [form, setForm] = useState<BuyerProfile>({ ...data });
  const [saving, setSaving] = useState(false);

  const set = (field: keyof BuyerProfile, value: unknown) =>
    setForm(prev => ({ ...prev, [field]: value }));

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
      <h3>Buyer Details</h3>
      <div className="form-grid">
        <label>
          <span>Pre-Approval Status</span>
          <select
            value={form.pre_approval_status}
            onChange={e => set('pre_approval_status', e.target.value as PreApprovalStatus)}
            disabled={disabled}
          >
            <option value="none">None</option>
            <option value="pre_qualified">Pre-Qualified</option>
            <option value="pre_approved">Pre-Approved</option>
            <option value="fully_approved">Fully Approved</option>
          </select>
        </label>
        <label>
          <span>Pre-Approval Amount</span>
          <input
            type="number"
            value={form.pre_approval_amount ?? ''}
            onChange={e => set('pre_approval_amount', e.target.value ? parseFloat(e.target.value) : undefined)}
            placeholder="$0.00"
            disabled={disabled}
          />
        </label>
        <label>
          <span>Pre-Approval Lender</span>
          <input
            type="text"
            value={form.pre_approval_lender || ''}
            onChange={e => set('pre_approval_lender', e.target.value)}
            placeholder="Lender name"
            disabled={disabled}
          />
        </label>
        <label>
          <span>Budget Min</span>
          <input
            type="number"
            value={form.purchase_budget_min ?? ''}
            onChange={e => set('purchase_budget_min', e.target.value ? parseFloat(e.target.value) : undefined)}
            placeholder="$0.00"
            disabled={disabled}
          />
        </label>
        <label>
          <span>Budget Max</span>
          <input
            type="number"
            value={form.purchase_budget_max ?? ''}
            onChange={e => set('purchase_budget_max', e.target.value ? parseFloat(e.target.value) : undefined)}
            placeholder="$0.00"
            disabled={disabled}
          />
        </label>
        <label>
          <span>First-Time Buyer</span>
          <select
            value={form.first_time_buyer === true ? 'yes' : form.first_time_buyer === false ? 'no' : ''}
            onChange={e => set('first_time_buyer', e.target.value === 'yes' ? true : e.target.value === 'no' ? false : undefined)}
            disabled={disabled}
          >
            <option value="">-- Select --</option>
            <option value="yes">Yes</option>
            <option value="no">No</option>
          </select>
        </label>
        <label>
          <span>Employment Status</span>
          <input
            type="text"
            value={form.employment_status || ''}
            onChange={e => set('employment_status', e.target.value)}
            placeholder="e.g., employed, self-employed"
            disabled={disabled}
          />
        </label>
        <label>
          <span>Employer Name</span>
          <input
            type="text"
            value={form.employer_name || ''}
            onChange={e => set('employer_name', e.target.value)}
            placeholder="Current employer"
            disabled={disabled}
          />
        </label>
        <label>
          <span>Annual Income</span>
          <input
            type="number"
            value={form.annual_income ?? ''}
            onChange={e => set('annual_income', e.target.value ? parseFloat(e.target.value) : undefined)}
            placeholder="$0.00"
            disabled={disabled}
          />
        </label>
      </div>
      <button
        className="btn-primary"
        onClick={handleSave}
        disabled={disabled || saving}
      >
        {saving ? 'Saving...' : 'Save Buyer Details'}
      </button>
    </div>
  );
}
