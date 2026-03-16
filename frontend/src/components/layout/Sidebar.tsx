import { NavLink } from 'react-router-dom';
import { useOnboardingContext } from '../../context/OnboardingContext';
import { ONBOARDING_STEPS } from '../../hooks/useOnboarding';

const NAV_ITEMS = [
  { to: '/dashboard', label: 'Dashboard', icon: '\u229E' },
  { to: '/extraction', label: 'Extraction', icon: '\u229C' },
  { to: '/transactions', label: 'Transactions', icon: '\u22A1' },
  { to: '/comparison', label: 'Comparison', icon: '\u22CF' },
  { to: '/profile', label: 'Profile', icon: '\u2299' },
  { to: '/profile/documents', label: 'Documents', icon: '\u229F' },
];

interface SidebarProps {
  open: boolean;
  onClose: () => void;
}

export function Sidebar({ open, onClose }: SidebarProps) {
  const { isOnboarding, currentStep } = useOnboardingContext();

  const activeOnboardingRoute = isOnboarding && currentStep
    ? ONBOARDING_STEPS.find((s) => s.id === currentStep)?.route ?? null
    : null;

  return (
    <>
      {/* Backdrop overlay — visible only on mobile when drawer is open */}
      <div
        className={`sidebar-backdrop ${open ? 'sidebar-backdrop-visible' : ''}`}
        onClick={onClose}
        aria-hidden="true"
      />
      <aside className={`sidebar ${open ? 'sidebar-open' : ''}`}>
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
    </>
  );
}
