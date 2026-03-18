/** Seller-specific profile form. */

import { useState } from 'react';
import { Button, SimpleGrid, Select } from '@mantine/core';
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
      <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm" mb="sm">
        <Select
          label="Ownership Type"
          value={form.ownership_type || null}
          onChange={(val) => setForm(prev => ({ ...prev, ownership_type: (val || undefined) as OwnershipType | undefined }))}
          data={[
            { value: 'sole', label: 'Sole Ownership' },
            { value: 'joint', label: 'Joint Ownership' },
            { value: 'trust', label: 'Trust' },
            { value: 'llc', label: 'LLC' },
          ]}
          placeholder="-- Select --"
          disabled={disabled}
          size="sm"
        />
      </SimpleGrid>
      <p className="form-hint">
        Property addresses will be populated from your transactions.
      </p>
      <Button
        variant="filled"
        color="cyan"
        onClick={handleSave}
        disabled={disabled || saving}
      >
        {saving ? 'Saving...' : 'Save Seller Details'}
      </Button>
    </div>
  );
}
