import type { QueryClient } from '@tanstack/react-query'
import { createRootRouteWithContext, createRoute, createRouter, redirect } from '@tanstack/react-router'
import { api } from '@/lib/api'
import { AppShell } from '@/components/AppShell'
import { LoginPage } from './LoginPage'
import { OrgPage } from '@/features/org/OrgPage'

const root = createRootRouteWithContext<{ queryClient: QueryClient }>()()

export const sessionQuery = { queryKey: ['session'], queryFn: api.me }

const login = createRoute({ getParentRoute: () => root, path: '/login', component: LoginPage })

const shell = createRoute({
  getParentRoute: () => root,
  id: 'shell',
  component: AppShell,
  beforeLoad: async ({ context }) => {
    try {
      await context.queryClient.fetchQuery(sessionQuery)
    } catch {
      throw redirect({ to: '/login' })
    }
  },
})
const home = createRoute({ getParentRoute: () => shell, path: '/', component: OrgPage })

const routeTree = root.addChildren([login, shell.addChildren([home])])
export const router = createRouter({ routeTree, context: { queryClient: undefined! } })

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}
