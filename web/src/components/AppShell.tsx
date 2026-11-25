import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, Outlet, useNavigate } from '@tanstack/react-router'
import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { FuelGauges } from '@/features/usage/FuelGauges'
import { LiveProvider, useLive } from '@/features/live/LiveContext'
import { api, setCsrf } from '@/lib/api'

function ConnDot() {
  const { conn } = useLive()
  return (
    <span role="status" className="flex items-center gap-1.5 text-xs text-muted-foreground">
      <span className={`size-2 rounded-full ${conn === 'live' ? 'bg-status-working' : 'bg-status-waiting'}`} />
      {conn === 'live' ? 'Live' : conn === 'connecting' ? 'Connecting' : 'Reconnecting'}
    </span>
  )
}

export function AppShell() {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const session = useQuery({ queryKey: ['session'], queryFn: api.me })
  if (session.data) setCsrf(session.data.csrf_token)
  const [dark, setDark] = useState(() => document.documentElement.classList.contains('dark'))
  const logout = useMutation({
    mutationFn: api.logout,
    onSuccess: () => {
      qc.clear()
      void navigate({ to: '/login' })
    },
  })
  const toggle = () => {
    const next = !dark
    document.documentElement.classList.toggle('dark', next)
    localStorage.setItem('theme', next ? 'dark' : 'light')
    setDark(next)
  }
  return (
    <LiveProvider>
    <div className="flex h-dvh flex-col bg-background text-foreground">
      <header className="flex items-center justify-between gap-2 border-b px-4 py-2">
        <nav aria-label="Main" className="flex items-center gap-4">
          <span className="font-semibold tracking-tight">AI Org</span>
          <Link to="/" className="text-sm text-muted-foreground hover:text-foreground [&.active]:font-medium [&.active]:text-foreground">Org chart</Link>
          <Link to="/tasks" className="text-sm text-muted-foreground hover:text-foreground [&.active]:font-medium [&.active]:text-foreground">Tasks</Link>
        </nav>
        <div className="flex items-center gap-2">
          <FuelGauges />
          <ConnDot />
          <Button variant="ghost" size="sm" onClick={toggle} aria-pressed={dark}>
            {dark ? 'Light mode' : 'Dark mode'}
          </Button>
          <Button variant="outline" size="sm" onClick={() => logout.mutate()}>
            Sign out
          </Button>
        </div>
      </header>
      <main className="min-h-0 flex-1">
        <Outlet />
      </main>
    </div>
    </LiveProvider>
  )
}
