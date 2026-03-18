import { useState, useEffect } from 'react';
import { NavLink } from 'react-router-dom';
import { Menu, useMantineColorScheme } from '@mantine/core';
import { useClerk } from '@clerk/clerk-react';
import { useOnboardingContext } from '../../context/OnboardingContext';
import { ONBOARDING_STEPS } from '../../hooks/useOnboarding';
import { useClerkAvatar } from '../../hooks/useClerkAvatar';
import { useDemoAuth } from '../../hooks/useDemoAuth';
import type { ProfileCompletion } from '../../api/profile';
import { getProfileCompletion } from '../../api/profile';
import { CompletionIndicator } from '../common/CompletionIndicator';

const CLERK_ENABLED = !!import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;

const NAV_ITEMS = [
  { to: '/transactions', label: 'Transactions', icon: 'T' },
  { to: '/comparison',   label: 'Comparison',   icon: 'C' },
];

function SunIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="4"/>
      <line x1="12" y1="2" x2="12" y2="5"/>
      <line x1="12" y1="19" x2="12" y2="22"/>
      <line x1="2" y1="12" x2="5" y2="12"/>
      <line x1="19" y1="12" x2="22" y2="12"/>
      <line x1="4.22" y1="4.22" x2="6.34" y2="6.34"/>
      <line x1="17.66" y1="17.66" x2="19.78" y2="19.78"/>
      <line x1="4.22" y1="19.78" x2="6.34" y2="17.66"/>
      <line x1="17.66" y1="6.34" x2="19.78" y2="4.22"/>
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
    </svg>
  );
}

function SidebarSettings() {
  const { colorScheme, toggleColorScheme } = useMantineColorScheme();
  const [completion, setCompletion] = useState<ProfileCompletion | null>(null);
  const { avatarUrl, clerkName } = useClerkAvatar();
  const { isDemoMode, demoUser, exitDemo } = useDemoAuth();
  const clerk = CLERK_ENABLED
    // eslint-disable-next-line react-hooks/rules-of-hooks
    ? useClerk()
    : null;

  const name = clerkName || demoUser?.name || 'User';
  const initials = name.split(' ').map((n: string) => n[0]).join('').slice(0, 2).toUpperCase();

  const clearOnboardingCache = () => {
    localStorage.removeItem('des_onboarding_v2');
    localStorage.removeItem('des_onboarding_step');
  };

  const handleLogout = async () => {
    clearOnboardingCache();

    if (isDemoMode) {
      exitDemo();
      return;
    }

    if (clerk) {
      await clerk.signOut();
      window.location.href = '/login';
    }
  };

  // Keep data-theme attribute in sync for legacy CSS still in App.css
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', colorScheme);
  }, [colorScheme]);

  useEffect(() => {
    getProfileCompletion().then(setCompletion).catch(() => {});
    const handler = () => getProfileCompletion().then(setCompletion).catch(() => {});
    window.addEventListener('profile-updated', handler);
    return () => window.removeEventListener('profile-updated', handler);
  }, []);

  return (
    <div className="sidebar-settings">
      {completion && completion.overall < 100 && (
        <div className="sidebar-completion">
          <CompletionIndicator percentage={completion.overall} label="Profile" size="sm" />
        </div>
      )}
      <Menu shadow="md" position="top-start" withArrow>
        <Menu.Target>
          <button
            className="sidebar-settings-btn"
            title="Profile & Settings"
            aria-label="Profile & Settings"
          >
            {avatarUrl ? (
              <img src={avatarUrl} className="sidebar-avatar-img" alt={name} />
            ) : (
              <span className="sidebar-avatar-initials">{initials}</span>
            )}
            <span className="sidebar-label">{name}</span>
          </button>
        </Menu.Target>
        <Menu.Dropdown>
          <Menu.Item renderRoot={(props) => <NavLink to="/profile" {...props} />}>
            My Profile
          </Menu.Item>
          <Menu.Item renderRoot={(props) => <NavLink to="/profile/documents" {...props} />}>
            My Documents
          </Menu.Item>
          <Menu.Divider />
          <Menu.Item
            leftSection={colorScheme === 'light' ? <MoonIcon /> : <SunIcon />}
            onClick={toggleColorScheme}
          >
            {colorScheme === 'light' ? 'Dark mode' : 'Light mode'}
          </Menu.Item>
          {(isDemoMode || clerk) && (
            <>
              <Menu.Divider />
              <Menu.Item color="red" onClick={() => void handleLogout()}>
                {isDemoMode ? 'Exit Demo' : 'Log Out'}
              </Menu.Item>
            </>
          )}
        </Menu.Dropdown>
      </Menu>
    </div>
  );
}

export function Sidebar() {
  const { isOnboarding, currentStep } = useOnboardingContext();

  const activeOnboardingRoute = isOnboarding && currentStep
    ? ONBOARDING_STEPS.find((s) => s.id === currentStep)?.route ?? null
    : null;

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <nav className="sidebar-nav">
        {NAV_ITEMS.map((item) => {
          const isOnboardingTarget = activeOnboardingRoute === item.to;
          return (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `sidebar-link${isActive ? ' sidebar-link-active' : ''}${isOnboardingTarget ? ' sidebar-link-onboarding-active' : ''}`
              }
            >
              <span className="sidebar-icon">{item.icon}</span>
              <span className="sidebar-label">{item.label}</span>
            </NavLink>
          );
        })}
      </nav>
      <div className="sidebar-footer" style={{ marginTop: 'auto' }}>
        <SidebarSettings />
      </div>
    </div>
  );
}
