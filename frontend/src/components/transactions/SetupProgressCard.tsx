import { Badge, Progress } from '@mantine/core';
import type { TransactionCompletionResult } from '../../api/transactions';

function bucketTone(status: 'complete' | 'partial' | 'missing'): string {
  if (status === 'complete') return 'green';
  if (status === 'partial') return 'yellow';
  return 'red';
}

interface SetupProgressCardProps {
  completion: TransactionCompletionResult;
}

export function SetupProgressCard({ completion }: SetupProgressCardProps) {
  return (
    <div className="setup-progress-card">
      <div className="setup-progress-header">
        <div>
          <div className="setup-progress-label">Setup Progress</div>
          <div className="setup-progress-copy">This measures setup completeness, not transaction safety.</div>
        </div>
        <div className="setup-progress-score">{Math.round(completion.overall)}%</div>
      </div>

      <Progress value={completion.overall} color="campari" size="md" radius="xl" />

      <div className="setup-progress-buckets">
        {completion.buckets.map((bucket) => (
          <div key={bucket.key} className="setup-progress-bucket">
            <div className="setup-progress-bucket-top">
              <span className="setup-progress-bucket-label">{bucket.label}</span>
              <Badge size="xs" color={bucketTone(bucket.status)} variant="light">
                {Math.round(bucket.score)}%
              </Badge>
            </div>
            <Progress value={bucket.score} color={bucketTone(bucket.status)} size="xs" radius="xl" />
          </div>
        ))}
      </div>

      {completion.blockers.length > 0 && (
        <div className="setup-progress-blockers">
          {completion.blockers.map((blocker) => (
            <div key={blocker} className="setup-progress-blocker">{blocker}</div>
          ))}
        </div>
      )}
    </div>
  );
}
