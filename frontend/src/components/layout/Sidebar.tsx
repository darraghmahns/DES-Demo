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
import {
  IconComparison,
  IconDocuments,
  IconLogout,
  IconMoon,
  IconSun,
  IconTransactions,
  IconUser,
} from '../common/AppIcons';
import { CompletionIndicator } from '../common/CompletionIndicator';

const CLERK_ENABLED = !!import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;

const NAV_ITEMS = [
  { to: '/transactions', label: 'Transactions', Icon: IconTransactions },
  { to: '/comparison', label: 'Comparison', Icon: IconComparison },
];

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
          <Menu.Item leftSection={<IconUser size={16} />} renderRoot={(props) => <NavLink to="/profile" {...props} />}>
            My Profile
          </Menu.Item>
          <Menu.Item leftSection={<IconDocuments size={16} />} renderRoot={(props) => <NavLink to="/profile/documents" {...props} />}>
            My Documents
          </Menu.Item>
          <Menu.Divider />
          <Menu.Item
            leftSection={colorScheme === 'light' ? <IconMoon size={16} /> : <IconSun size={16} />}
            onClick={toggleColorScheme}
          >
            {colorScheme === 'light' ? 'Dark mode' : 'Light mode'}
          </Menu.Item>
          {(isDemoMode || clerk) && (
            <>
              <Menu.Divider />
              <Menu.Item leftSection={<IconLogout size={16} />} color="red" onClick={() => void handleLogout()}>
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
          const Icon = item.Icon;
          return (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `sidebar-link${isActive ? ' sidebar-link-active' : ''}${isOnboardingTarget ? ' sidebar-link-onboarding-active' : ''}`
              }
            >
              <span className="sidebar-icon"><Icon size={18} /></span>
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
