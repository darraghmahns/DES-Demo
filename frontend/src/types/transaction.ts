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
  created_by: string;
  org_id?: string;
  created_at: string;
  updated_at: string;
}
