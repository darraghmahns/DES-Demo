/** User Management TypeScript types — mirrors backend schemas.py models. */

export type UserType = 'buyer' | 'seller' | 'agent' | 'loan_officer';

export type UserDocumentType =
  | 'pre_approval_letter'
  | 'bank_statement'
  | 'pay_stub'
  | 'tax_return'
  | 'w2'
  | 'proof_of_funds'
  | 'drivers_license'
  | 'proof_of_insurance'
  | 'other';

export type PreApprovalStatus = 'none' | 'pre_qualified' | 'pre_approved' | 'fully_approved';
export type OwnershipType = 'sole' | 'joint' | 'trust' | 'llc';

export interface AgentProfile {
  license_number?: string;
  license_state?: string;
  license_expiry?: string;
  brokerage_name?: string;
  brokerage_id?: string;
  mls_id?: string;
  nar_member_id?: string;
  areas_served: string[];
}

export interface BuyerProfile {
  pre_approval_status: PreApprovalStatus;
  pre_approval_amount?: number;
  pre_approval_lender?: string;
  purchase_budget_min?: number;
  purchase_budget_max?: number;
  property_preferences?: Record<string, unknown>;
  first_time_buyer?: boolean;
  employment_status?: string;
  employer_name?: string;
  annual_income?: number;
}

export interface SellerProfile {
  property_addresses: Record<string, string>[];
  ownership_type?: OwnershipType;
}

export interface LoanOfficerProfile {
  nmls_id?: string;
  company_name?: string;
  company_nmls?: string;
  license_states: string[];
  loan_types_offered: string[];
  contact_preference?: string;
}

export interface UserProfile {
  _id: string;
  clerk_user_id?: string;
  email: string;
  name: string;
  phone?: string;
  address?: Record<string, string>;
  profile_photo_url?: string;
  user_types: UserType[];
  agent_profile?: AgentProfile;
  buyer_profile?: BuyerProfile;
  seller_profile?: SellerProfile;
  loan_officer_profile?: LoanOfficerProfile;
  has_clerk_account: boolean;
  org_id?: string;
  org_name?: string;
  created_at: string;
  last_login?: string;
}
