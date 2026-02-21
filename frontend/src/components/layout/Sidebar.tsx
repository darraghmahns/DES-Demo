import { NavLink } from 'react-router-dom';
import { useOnboardingContext } from '../../context/OnboardingContext';
import { ONBOARDING_STEPS } from '../../hooks/useOnboarding';

const NAV_ITEMS = [
  { to: '/dashboard', label: 'Dashboard', icon: '\u229E' },
  { to: '/extraction', label: 'Extraction', icon: '\u229C' },
  { to: '/transactions', label: 'Transactions', icon: '\u22A1' },
  { to: '/profile', label: 'Profile', icon: '\u2299' },
  { to: '/profile/documents', label: 'Documents', icon: '\u229F' },
];

export function Sidebar() {
  const { isOnboarding, currentStep } = useOnboardingContext();

  // Determine which nav route the current onboarding step targets
  const activeOnboardingRoute = isOnboarding && currentStep
    ? ONBOARDING_STEPS.find((s) => s.id === currentStep)?.route ?? null
    : null;

  return (
    <aside className="sidebar">
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
    </aside>
  );
}
