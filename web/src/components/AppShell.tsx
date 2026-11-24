import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Outlet, useNavigate } from '@tanstack/react-router'
import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { api, setCsrf } from '@/lib/api'

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
    <div className="flex h-dvh flex-col bg-background text-foreground">
      <header className="flex items-center justify-between border-b px-4 py-2">
        <span className="font-semibold tracking-tight">AI Org</span>
        <div className="flex items-center gap-2">
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
  )
}
