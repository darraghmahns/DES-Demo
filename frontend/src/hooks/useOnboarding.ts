/** Hook managing onboarding wizard state, API sync, and localStorage persistence. */

import { useState, useEffect, useCallback, useRef } from 'react';
import type { OnboardingStepId, OnboardingStepStatus, OnboardingStatus } from '../api';
import { fetchOnboardingStatus, updateOnboardingStep } from '../api';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const STORAGE_KEY = 'des_onboarding_v2';

/** Ordered step definitions — route each step navigates to. */
export const ONBOARDING_STEPS: { id: OnboardingStepId; route: string }[] = [
  { id: 'welcome', route: '/dashboard' },
  { id: 'profile', route: '/profile' },
  { id: 'documents', route: '/profile/documents' },
  { id: 'extraction', route: '/extraction' },
  { id: 'complete', route: '/dashboard' },
];

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface UseOnboardingReturn {
  /** Whether onboarding is active (not completed and not permanently dismissed). */
  isOnboarding: boolean;
  /** Current step ID, or null if not onboarding. */
  currentStep: OnboardingStepId | null;
  /** Current step index (0-based). */
  currentStepIndex: number;
  /** Step status array from backend. */
  steps: OnboardingStepStatus[];
  /** Whether the side panel is visible. */
  panelOpen: boolean;
  /** Whether we're still loading initial status. */
  loading: boolean;
  /** Integration connection status (for the complete step summary). */
  dotloopConnected: boolean;

  /** Mark current step completed and advance. */
  advanceStep: () => Promise<void>;
  /** Mark current step skipped and advance. */
  skipStep: () => Promise<void>;
  /** Minimize the panel (user can reopen). */
  dismissPanel: () => void;
  /** Reopen the panel after dismissal. */
  openPanel: () => void;
  /** Pages call this to report user actions during onboarding. */
  markStepAction: (action: string) => void;
}

// ---------------------------------------------------------------------------
// localStorage helpers
// ---------------------------------------------------------------------------

interface PersistedState {
  currentStepIndex: number;
  dismissed: boolean;
}

function loadPersistedState(): PersistedState | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as PersistedState;
  } catch {
    return null;
  }
}

function persistState(state: PersistedState): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // localStorage unavailable — ignore
  }
}

function clearPersistedState(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
    // Also clear legacy v1 key
    localStorage.removeItem('des_onboarding_step');
  } catch {
    // ignore
  }
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useOnboarding(): UseOnboardingReturn {
  const [loading, setLoading] = useState(true);
  const [completed, setCompleted] = useState(true); // fail-open default
  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [steps, setSteps] = useState<OnboardingStepStatus[]>([]);
  const [panelOpen, setPanelOpen] = useState(false);
  const [dotloopConnected, setDotloopConnected] = useState(false);

  // Track step actions from pages (e.g. "name_set", "document_uploaded")
  const stepActionsRef = useRef<Set<string>>(new Set());

  // ── Fetch status on mount ──
  useEffect(() => {
    let cancelled = false;

    async function init() {
      const status: OnboardingStatus = await fetchOnboardingStatus();

      if (cancelled) return;

      setDotloopConnected(status.dotloop_connected);

      if (status.completed) {
        setCompleted(true);
        setLoading(false);
        clearPersistedState();
        return;
      }

      // Onboarding active — restore local state or use backend
      setCompleted(false);
      setSteps(status.steps);

      const persisted = loadPersistedState();
      const stepIdx = persisted?.currentStepIndex ?? status.current_step;
      // Clamp to valid range
      const clampedIdx = Math.min(Math.max(0, stepIdx), ONBOARDING_STEPS.length - 1);
      setCurrentStepIndex(clampedIdx);

      const dismissed = persisted?.dismissed ?? false;
      setPanelOpen(!dismissed);

      setLoading(false);
    }

    init();
    return () => { cancelled = true; };
  }, []);

  // ── Persist to localStorage on state changes ──
  useEffect(() => {
    if (loading || completed) return;
    persistState({ currentStepIndex, dismissed: !panelOpen });
  }, [currentStepIndex, panelOpen, loading, completed]);

  // ── Advance to next step (mark current as completed) ──
  const advanceStep = useCallback(async () => {
    if (completed || currentStepIndex >= ONBOARDING_STEPS.length) return;

    const stepId = ONBOARDING_STEPS[currentStepIndex].id;

    try {
      const updated = await updateOnboardingStep(stepId, 'completed');
      setSteps(updated.steps);

      if (updated.completed) {
        setCompleted(true);
        setPanelOpen(false);
        clearPersistedState();
        return;
      }
    } catch {
      // API failed — still advance locally so user isn't stuck
    }

    const nextIdx = currentStepIndex + 1;
    if (nextIdx >= ONBOARDING_STEPS.length) {
      // All steps done
      setCompleted(true);
      setPanelOpen(false);
      clearPersistedState();
    } else {
      setCurrentStepIndex(nextIdx);
    }

    stepActionsRef.current.clear();
  }, [completed, currentStepIndex]);

  // ── Skip current step ──
  const skipStep = useCallback(async () => {
    if (completed || currentStepIndex >= ONBOARDING_STEPS.length) return;

    const stepId = ONBOARDING_STEPS[currentStepIndex].id;

    try {
      const updated = await updateOnboardingStep(stepId, 'skipped');
      setSteps(updated.steps);

      if (updated.completed) {
        setCompleted(true);
        setPanelOpen(false);
        clearPersistedState();
        return;
      }
    } catch {
      // API failed — still advance locally
    }

    const nextIdx = currentStepIndex + 1;
    if (nextIdx >= ONBOARDING_STEPS.length) {
      setCompleted(true);
      setPanelOpen(false);
      clearPersistedState();
    } else {
      setCurrentStepIndex(nextIdx);
    }

    stepActionsRef.current.clear();
  }, [completed, currentStepIndex]);

  // ── Panel visibility ──
  const dismissPanel = useCallback(() => {
    setPanelOpen(false);
  }, []);

  const openPanel = useCallback(() => {
    if (!completed) setPanelOpen(true);
  }, [completed]);

  // ── Mark step action (called by pages) ──
  const markStepAction = useCallback((action: string) => {
    stepActionsRef.current.add(action);
  }, []);

  // ── Derived values ──
  const isOnboarding = !completed && !loading;
  const currentStep: OnboardingStepId | null =
    isOnboarding ? ONBOARDING_STEPS[currentStepIndex]?.id ?? null : null;

  return {
    isOnboarding,
    currentStep,
    currentStepIndex,
    steps,
    panelOpen,
    loading,
    dotloopConnected,
    advanceStep,
    skipStep,
    dismissPanel,
    openPanel,
    markStepAction,
  };
}
