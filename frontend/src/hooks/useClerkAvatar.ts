/** Safe wrapper around Clerk's useUser() for avatar display.
 *
 * Returns the Clerk user's avatar URL when ClerkProvider is present,
 * or undefined when Clerk is disabled (dev/e2e mode). This avoids
 * the crash that happens when useUser() is called without a provider.
 */

import { useUser } from '@clerk/clerk-react';

const CLERK_ENABLED = !!import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;

export function useClerkAvatar(): { avatarUrl?: string; clerkName?: string } {
  // When Clerk is disabled, the hook import is still valid but calling
  // useUser() would crash without a ClerkProvider. We guard at runtime.
  if (!CLERK_ENABLED) {
    return {};
  }

  // eslint-disable-next-line react-hooks/rules-of-hooks
  const { user } = useUser();
  return {
    avatarUrl: user?.imageUrl,
    clerkName: user?.fullName ?? undefined,
  };
}
