/** Onboarding context — lets pages report user actions to the onboarding orchestrator. */

import { createContext, useContext } from 'react';
import type { OnboardingStepId } from '../api';

export interface OnboardingContextValue {
  /** Whether the onboarding wizard is currently active. */
  isOnboarding: boolean;
  /** The current step ID, or null if not onboarding. */
  currentStep: OnboardingStepId | null;
  /** Pages call this to report user actions (e.g. "name_set", "role_selected"). */
  markStepAction: (action: string) => void;
}

const OnboardingContext = createContext<OnboardingContextValue | null>(null);

export function OnboardingProvider({
  value,
  children,
}: {
  value: OnboardingContextValue;
  children: React.ReactNode;
}) {
  return (
    <OnboardingContext.Provider value={value}>
      {children}
    </OnboardingContext.Provider>
  );
}

/**
 * Consume the onboarding context. Returns a safe default when used outside
 * the provider (e.g. in e2e tests where onboarding is disabled).
 */
export function useOnboardingContext(): OnboardingContextValue {
  const ctx = useContext(OnboardingContext);
  if (!ctx) {
    // Safe fallback — pages can always call markStepAction without crashing
    return { isOnboarding: false, currentStep: null, markStepAction: () => {} };
  }
  return ctx;
}
