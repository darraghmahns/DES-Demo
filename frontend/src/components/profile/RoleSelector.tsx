/** Role selector: add/remove roles from user profile. */

import type { UserType } from '../../types/user';

interface RoleSelectorProps {
  currentRoles: UserType[];
  onAddRole: (role: UserType) => void;
  onRemoveRole: (role: UserType) => void;
  disabled?: boolean;
}

const ALL_ROLES: { value: UserType; label: string; icon: string; desc: string }[] = [
  { value: 'agent', label: 'Agent', icon: 'A', desc: 'Real estate agent or broker' },
  { value: 'buyer', label: 'Buyer', icon: 'B', desc: 'Property buyer' },
  { value: 'seller', label: 'Seller', icon: 'S', desc: 'Property seller' },
  { value: 'loan_officer', label: 'Loan Officer', icon: 'L', desc: 'Mortgage loan officer' },
];

export function RoleSelector({ currentRoles, onAddRole, onRemoveRole, disabled }: RoleSelectorProps) {
  return (
    <div className="role-selector">
      <h3>My Roles</h3>
      <div className="role-chips">
        {ALL_ROLES.map(role => {
          const active = currentRoles.includes(role.value);
          return (
            <button
              key={role.value}
              className={`role-chip ${active ? 'role-chip-active' : ''}`}
              onClick={() => active ? onRemoveRole(role.value) : onAddRole(role.value)}
              disabled={disabled}
              title={role.desc}
            >
              <span className="role-chip-icon">{role.icon}</span>
              <span className="role-chip-label">{role.label}</span>
              <span className="role-chip-action">{active ? '×' : '+'}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
