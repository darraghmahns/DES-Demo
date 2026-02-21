import { useParams } from 'react-router-dom';

export function TransactionDetail() {
  const { id } = useParams<{ id: string }>();

  return (
    <div className="page-transaction-detail">
      <h1>Transaction Detail</h1>
      <p className="page-subtitle">Transaction ID: {id}</p>

      <div className="placeholder-card">
        <p>Transaction lobby coming in Phase 3.</p>
        <p>This will include:</p>
        <ul>
          <li>Participant sidebar with completion indicators</li>
          <li>Tabbed view: Overview, Documents, Compliance, Activity</li>
          <li>Auto-fill from participant profiles</li>
          <li>Status progression controls</li>
        </ul>
      </div>
    </div>
  );
}
