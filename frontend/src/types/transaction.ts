/** Transaction TypeScript types — mirrors backend schemas.py models. */

export type TransactionStatus =
  | 'draft'
  | 'active'
  | 'under_contract'
  | 'pending_close'
  | 'closed'
  | 'cancelled'
  | 'expired';

export type ParticipantStatus = 'invited' | 'active' | 'removed';
export type InvitationStatus = 'created' | 'sent' | 'opened' | 'accepted' | 'expired' | 'revoked' | 'failed';
export type DotloopSyncStatus = 'never' | 'current' | 'stale' | 'error';

export type ParticipantRole =
  | 'BUYER'
  | 'SELLER'
  | 'LISTING_AGENT'
  | 'BUYING_AGENT'
  | 'LISTING_BROKER'
  | 'BUYING_BROKER'
  | 'ESCROW_TITLE_REP'
  | 'LOAN_OFFICER'
  | 'APPRAISER'
  | 'INSPECTOR'
  | 'TRANSACTION_COORDINATOR'
  | 'OTHER';

export interface TransactionParticipant {
  user_id: string;
  role: ParticipantRole;
  status: ParticipantStatus;
  added_at?: string;
  added_by?: string;
  removed_at?: string;
  profile_completion?: number;
}

export interface PropertyAddress {
  street_number: string;
  street_name: string;
  unit_number?: string;
  city: string;
  state_or_province: string;
  postal_code: string;
  country?: string;
  county?: string;
  mls_number?: string;
  parcel_tax_id?: string;
}

export interface Transaction {
  _id: string;
  name: string;
  transaction_type: string;
  status: TransactionStatus;
  property_address?: PropertyAddress;
  mls_number?: string;
  participants: TransactionParticipant[];
  purchase_price?: number;
  earnest_money?: number;
  closing_date?: string;
  extraction_ids?: string[];
  agent_side?: 'buyer' | 'seller';
  dotloop_loop_id?: string;
  dotloop_sync_status?: DotloopSyncStatus;
  dotloop_last_synced_at?: string | null;
  dotloop_last_remote_updated_at?: string | null;
  dotloop_sync_error?: string | null;
  created_by: string;
  org_id?: string;
  created_at: string;
  updated_at: string;
}

export interface TransactionInvitation {
  id: string;
  transaction_id: string;
  invitee_user_id?: string | null;
  email: string;
  name?: string | null;
  role: ParticipantRole;
  status: InvitationStatus;
  expires_at?: string | null;
  sent_at?: string | null;
  opened_at?: string | null;
  accepted_at?: string | null;
  revoked_at?: string | null;
  provider?: string | null;
  provider_message_id?: string | null;
  last_error?: string | null;
  invite_url?: string | null;
}

export const STATUS_LABELS: Record<TransactionStatus, string> = {
  draft: 'Draft',
  active: 'Active',
  under_contract: 'Under Contract',
  pending_close: 'Pending Close',
  closed: 'Closed',
  cancelled: 'Cancelled',
  expired: 'Expired',
};

export const ROLE_LABELS: Record<ParticipantRole, string> = {
  BUYER: 'Buyer',
  SELLER: 'Seller',
  LISTING_AGENT: 'Listing Agent',
  BUYING_AGENT: 'Buying Agent',
  LISTING_BROKER: 'Listing Broker',
  BUYING_BROKER: 'Buying Broker',
  ESCROW_TITLE_REP: 'Escrow/Title',
  LOAN_OFFICER: 'Loan Officer',
  APPRAISER: 'Appraiser',
  INSPECTOR: 'Inspector',
  TRANSACTION_COORDINATOR: 'TC',
  OTHER: 'Other',
};

export const STATUS_COLORS: Record<TransactionStatus, string> = {
  draft: 'gray',
  active: 'green',
  under_contract: 'blue',
  pending_close: 'yellow',
  closed: 'green',
  cancelled: 'red',
  expired: 'red',
};

export const DOTLOOP_SYNC_LABELS: Record<DotloopSyncStatus, string> = {
  never: 'Linked',
  current: 'Up to Date',
  stale: 'Needs Review',
  error: 'Sync Failed',
};
