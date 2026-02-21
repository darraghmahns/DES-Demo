/** Hook for profile CRUD operations. */

import { useState, useEffect, useCallback } from 'react';
import type { UserProfile, UserType } from '../types/user';
import type { ProfileCompletion, ProfileUpdateRequest } from '../api/profile';
import {
  getProfile,
  updateProfile as apiUpdateProfile,
  updateAgentProfile,
  updateBuyerProfile,
  updateSellerProfile,
  updateLoanOfficerProfile,
  addRole as apiAddRole,
  removeRole as apiRemoveRole,
  getProfileCompletion,
} from '../api/profile';

interface UseProfileReturn {
  profile: UserProfile | null;
  completion: ProfileCompletion | null;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  updateSharedFields: (data: ProfileUpdateRequest) => Promise<void>;
  updateRoleProfile: (role: UserType, data: unknown) => Promise<void>;
  addRole: (role: UserType) => Promise<void>;
  removeRole: (role: UserType) => Promise<void>;
}

export function useProfile(): UseProfileReturn {
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [completion, setCompletion] = useState<ProfileCompletion | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const [p, c] = await Promise.all([getProfile(), getProfileCompletion()]);
      setProfile(p);
      setCompletion(c);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load profile');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const updateSharedFields = useCallback(async (data: ProfileUpdateRequest) => {
    try {
      setError(null);
      const updated = await apiUpdateProfile(data);
      setProfile(updated);
      const c = await getProfileCompletion();
      setCompletion(c);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to update profile');
      throw e;
    }
  }, []);

  const updateRoleProfile = useCallback(async (role: UserType, data: unknown) => {
    try {
      setError(null);
      const updaters: Record<UserType, (d: never) => Promise<UserProfile>> = {
        agent: updateAgentProfile as (d: never) => Promise<UserProfile>,
        buyer: updateBuyerProfile as (d: never) => Promise<UserProfile>,
        seller: updateSellerProfile as (d: never) => Promise<UserProfile>,
        loan_officer: updateLoanOfficerProfile as (d: never) => Promise<UserProfile>,
      };
      const updated = await updaters[role](data as never);
      setProfile(updated);
      const c = await getProfileCompletion();
      setCompletion(c);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to update role profile');
      throw e;
    }
  }, []);

  const addRole = useCallback(async (role: UserType) => {
    try {
      setError(null);
      const updated = await apiAddRole(role);
      setProfile(updated);
      const c = await getProfileCompletion();
      setCompletion(c);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to add role');
      throw e;
    }
  }, []);

  const removeRole = useCallback(async (role: UserType) => {
    try {
      setError(null);
      const updated = await apiRemoveRole(role);
      setProfile(updated);
      const c = await getProfileCompletion();
      setCompletion(c);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to remove role');
      throw e;
    }
  }, []);

  return {
    profile,
    completion,
    loading,
    error,
    refresh,
    updateSharedFields,
    updateRoleProfile,
    addRole,
    removeRole,
  };
}
