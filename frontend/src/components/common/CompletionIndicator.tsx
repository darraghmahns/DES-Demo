/** Circular/bar completion percentage indicator. */

import { Progress, Group, Text } from '@mantine/core';

interface CompletionIndicatorProps {
  percentage: number;
  label?: string;
  size?: 'sm' | 'md' | 'lg';
}

export function CompletionIndicator({ percentage, label, size = 'md' }: CompletionIndicatorProps) {
  const clamped = Math.min(100, Math.max(0, percentage));
  const color = clamped >= 80 ? 'green' : clamped >= 50 ? 'yellow' : 'red';
  const progressSize = size === 'sm' ? 'xs' : size === 'md' ? 'sm' : 'md';

  return (
    <div>
      <Group justify="space-between" mb={4}>
        {label && <Text size="xs" c="dimmed">{label}</Text>}
        <Text size="xs" c={color} fw={500}>{Math.round(clamped)}%</Text>
      </Group>
      <Progress value={clamped} color={color} size={progressSize} />
    </div>
  );
}
