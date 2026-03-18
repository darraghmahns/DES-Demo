/** Agent-specific profile form. */

import { useState } from 'react';
import { Button, SimpleGrid, TextInput } from '@mantine/core';
import type { AgentProfile } from '../../types/user';

interface AgentFormProps {
  data: AgentProfile;
  onSave: (data: AgentProfile) => Promise<void>;
  disabled?: boolean;
}

export function AgentForm({ data, onSave, disabled }: AgentFormProps) {
  const [form, setForm] = useState<AgentProfile>({ ...data });
  const [saving, setSaving] = useState(false);

  const set = (field: keyof AgentProfile, value: string) =>
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
      <h3>Agent Details</h3>
      <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm" mb="sm">
        <TextInput
          label="License Number"
          value={form.license_number || ''}
          onChange={e => set('license_number', e.target.value)}
          placeholder="e.g., RE-12345678"
          disabled={disabled}
          size="sm"
        />
        <TextInput
          label="License State"
          value={form.license_state || ''}
          onChange={e => set('license_state', e.target.value)}
          placeholder="e.g., CA"
          maxLength={2}
          disabled={disabled}
          size="sm"
        />
        <TextInput
          label="Brokerage Name"
          value={form.brokerage_name || ''}
          onChange={e => set('brokerage_name', e.target.value)}
          placeholder="e.g., Keller Williams"
          disabled={disabled}
          size="sm"
        />
        <TextInput
          label="MLS ID"
          value={form.mls_id || ''}
          onChange={e => set('mls_id', e.target.value)}
          placeholder="MLS member ID"
          disabled={disabled}
          size="sm"
        />
        <TextInput
          label="NAR Member ID"
          value={form.nar_member_id || ''}
          onChange={e => set('nar_member_id', e.target.value)}
          placeholder="NAR member ID"
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
        {saving ? 'Saving...' : 'Save Agent Details'}
      </Button>
    </div>
  );
}
