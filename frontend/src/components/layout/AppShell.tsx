import { Outlet } from 'react-router-dom';
import { Navbar } from './Navbar';
import { Sidebar } from './Sidebar';

export function AppShell() {
  return (
    <div className="app-shell">
      <Navbar />
      <div className="app-shell-body">
        <Sidebar />
        <main className="app-shell-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
