import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { ClerkProvider } from '@clerk/clerk-react'
import { MantineProvider } from '@mantine/core'
import '@mantine/core/styles.css'
import App from './App.tsx'
import './App.css'
import { desTheme } from './theme'

const storedScheme = localStorage.getItem('mantine-color-scheme') ?? 'light';
document.documentElement.setAttribute('data-theme', storedScheme);

const PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY

const root = document.getElementById('root')!

// If no Clerk key configured, render app directly (dev mode)
if (PUBLISHABLE_KEY) {
  createRoot(root).render(
    <StrictMode>
      <MantineProvider theme={desTheme} defaultColorScheme="light">
        <ClerkProvider publishableKey={PUBLISHABLE_KEY}>
          <App />
        </ClerkProvider>
      </MantineProvider>
    </StrictMode>,
  )
} else {
  createRoot(root).render(
    <StrictMode>
      <MantineProvider theme={desTheme} defaultColorScheme="light">
        <App />
      </MantineProvider>
    </StrictMode>,
  )
}
