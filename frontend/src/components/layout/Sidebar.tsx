import { NavLink } from 'react-router-dom';

const NAV_ITEMS = [
  { to: '/dashboard', label: 'Dashboard', icon: '⊞' },
  { to: '/extraction', label: 'Extraction', icon: '⊜' },
  { to: '/transactions', label: 'Transactions', icon: '⊡' },
  { to: '/profile', label: 'Profile', icon: '⊙' },
  { to: '/profile/documents', label: 'Documents', icon: '⊟' },
];

export function Sidebar() {
  return (
    <aside className="sidebar">
      <nav className="sidebar-nav">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              `sidebar-link ${isActive ? 'sidebar-link-active' : ''}`
            }
          >
            <span className="sidebar-icon">{item.icon}</span>
            <span className="sidebar-label">{item.label}</span>
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
