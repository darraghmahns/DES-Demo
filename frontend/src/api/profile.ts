/** Profile API functions for D.E.S. */

import { apiFetch } from './client';
import type { UserProfile, UserType, AgentProfile, BuyerProfile, SellerProfile, LoanOfficerProfile } from '../types/user';

export interface ProfileCompletion {
  overall: number;
  roles: Record<string, number>;
  missing_fields: Record<string, string[]>;
}

export interface ProfileUpdateRequest {
  name?: string;
  phone?: string;
  address?: Record<string, string>;
  profile_photo_url?: string;
}

export interface UserSearchResult {
  _id: string;
  email: string;
  name: string;
  user_types: UserType[];
  profile_photo_url?: string;
}

export async function getProfile(): Promise<UserProfile> {
  return apiFetch<UserProfile>('/api/profile');
}

export async function updateProfile(data: ProfileUpdateRequest): Promise<UserProfile> {
  return apiFetch<UserProfile>('/api/profile', {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function updateAgentProfile(data: AgentProfile): Promise<UserProfile> {
  return apiFetch<UserProfile>('/api/profile/agent', {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function updateBuyerProfile(data: BuyerProfile): Promise<UserProfile> {
  return apiFetch<UserProfile>('/api/profile/buyer', {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function updateSellerProfile(data: SellerProfile): Promise<UserProfile> {
  return apiFetch<UserProfile>('/api/profile/seller', {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function updateLoanOfficerProfile(data: LoanOfficerProfile): Promise<UserProfile> {
  return apiFetch<UserProfile>('/api/profile/loan-officer', {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function addRole(role: UserType): Promise<UserProfile> {
  return apiFetch<UserProfile>('/api/profile/roles', {
    method: 'POST',
    body: JSON.stringify({ role }),
  });
}

export async function removeRole(role: UserType): Promise<UserProfile> {
  return apiFetch<UserProfile>(`/api/profile/roles/${role}`, {
    method: 'DELETE',
  });
}

export async function getProfileCompletion(): Promise<ProfileCompletion> {
  return apiFetch<ProfileCompletion>('/api/profile/completion');
}

export async function getUserById(userId: string): Promise<UserProfile> {
  return apiFetch<UserProfile>(`/api/users/${userId}`);
}

export async function searchUsers(email: string): Promise<UserSearchResult[]> {
  return apiFetch<UserSearchResult[]>(`/api/users/search?email=${encodeURIComponent(email)}`);
}
