import { useEffect } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { AppShell as MantineAppShell } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { Navbar } from './Navbar';
import { Sidebar } from './Sidebar';
import { OnboardingOrchestrator } from '../onboarding/OnboardingOrchestrator';

export function AppShell() {
  const [opened, { toggle, close }] = useDisclosure();
  const location = useLocation();

  // Close mobile drawer on route change
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { close(); }, [location.pathname]);

  return (
    <OnboardingOrchestrator onMobileNavOpen={opened} onMobileNavClose={close}>
      <MantineAppShell
        header={{ height: 52 }}
        navbar={{ width: 200, breakpoint: 'sm', collapsed: { mobile: !opened } }}
      >
        <MantineAppShell.Header>
          <Navbar onMenuToggle={toggle} drawerOpen={opened} />
        </MantineAppShell.Header>
        <MantineAppShell.Navbar p="sm">
          <Sidebar />
        </MantineAppShell.Navbar>
        <MantineAppShell.Main>
          <div style={{ padding: '24px' }}>
            <Outlet />
          </div>
        </MantineAppShell.Main>
      </MantineAppShell>
    </OnboardingOrchestrator>
  );
}
