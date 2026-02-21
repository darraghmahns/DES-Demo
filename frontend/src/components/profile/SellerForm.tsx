/** Seller-specific profile form. */

import { useState } from 'react';
import type { SellerProfile, OwnershipType } from '../../types/user';

interface SellerFormProps {
  data: SellerProfile;
  onSave: (data: SellerProfile) => Promise<void>;
  disabled?: boolean;
}

export function SellerForm({ data, onSave, disabled }: SellerFormProps) {
  const [form, setForm] = useState<SellerProfile>({ ...data });
  const [saving, setSaving] = useState(false);

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
      <h3>Seller Details</h3>
      <div className="form-grid">
        <label>
          <span>Ownership Type</span>
          <select
            value={form.ownership_type || ''}
            onChange={e => setForm(prev => ({ ...prev, ownership_type: (e.target.value || undefined) as OwnershipType | undefined }))}
            disabled={disabled}
          >
            <option value="">-- Select --</option>
            <option value="sole">Sole Ownership</option>
            <option value="joint">Joint Ownership</option>
            <option value="trust">Trust</option>
            <option value="llc">LLC</option>
          </select>
        </label>
      </div>
      <p className="form-hint">
        Property addresses will be populated from your transactions.
      </p>
      <button
        className="btn-primary"
        onClick={handleSave}
        disabled={disabled || saving}
      >
        {saving ? 'Saving...' : 'Save Seller Details'}
      </button>
    </div>
  );
}
