/** Buyer-specific profile form. */

import { useState } from 'react';
import { Button, SimpleGrid, TextInput, NumberInput, Select } from '@mantine/core';
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
      <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm" mb="sm">
        <Select
          label="Pre-Approval Status"
          value={form.pre_approval_status}
          onChange={(val) => set('pre_approval_status', val as PreApprovalStatus)}
          data={[
            { value: 'none', label: 'None' },
            { value: 'pre_qualified', label: 'Pre-Qualified' },
            { value: 'pre_approved', label: 'Pre-Approved' },
            { value: 'fully_approved', label: 'Fully Approved' },
          ]}
          disabled={disabled}
          size="sm"
        />
        <NumberInput
          label="Pre-Approval Amount"
          value={form.pre_approval_amount ?? ''}
          onChange={(val) => set('pre_approval_amount', val === '' ? undefined : Number(val))}
          placeholder="$0.00"
          disabled={disabled}
          size="sm"
        />
        <TextInput
          label="Pre-Approval Lender"
          value={form.pre_approval_lender || ''}
          onChange={e => set('pre_approval_lender', e.target.value)}
          placeholder="Lender name"
          disabled={disabled}
          size="sm"
        />
        <NumberInput
          label="Budget Min"
          value={form.purchase_budget_min ?? ''}
          onChange={(val) => set('purchase_budget_min', val === '' ? undefined : Number(val))}
          placeholder="$0.00"
          disabled={disabled}
          size="sm"
        />
        <NumberInput
          label="Budget Max"
          value={form.purchase_budget_max ?? ''}
          onChange={(val) => set('purchase_budget_max', val === '' ? undefined : Number(val))}
          placeholder="$0.00"
          disabled={disabled}
          size="sm"
        />
        <Select
          label="First-Time Buyer"
          value={form.first_time_buyer === true ? 'yes' : form.first_time_buyer === false ? 'no' : null}
          onChange={(val) => set('first_time_buyer', val === 'yes' ? true : val === 'no' ? false : undefined)}
          data={[
            { value: 'yes', label: 'Yes' },
            { value: 'no', label: 'No' },
          ]}
          placeholder="-- Select --"
          disabled={disabled}
          size="sm"
        />
        <TextInput
          label="Employment Status"
          value={form.employment_status || ''}
          onChange={e => set('employment_status', e.target.value)}
          placeholder="e.g., employed, self-employed"
          disabled={disabled}
          size="sm"
        />
        <TextInput
          label="Employer Name"
          value={form.employer_name || ''}
          onChange={e => set('employer_name', e.target.value)}
          placeholder="Current employer"
          disabled={disabled}
          size="sm"
        />
        <NumberInput
          label="Annual Income"
          value={form.annual_income ?? ''}
          onChange={(val) => set('annual_income', val === '' ? undefined : Number(val))}
          placeholder="$0.00"
          disabled={disabled}
          size="sm"
        />
      </SimpleGrid>
      <Button
        variant="filled"
        color="cyan"
        onClick={handleSave}
        disabled={disabled || saving}
      >
        {saving ? 'Saving...' : 'Save Buyer Details'}
      </Button>
    </div>
  );
}
