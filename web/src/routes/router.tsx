import type { QueryClient } from '@tanstack/react-query'
import { createRootRouteWithContext, createRoute, createRouter, redirect } from '@tanstack/react-router'
import { api } from '@/lib/api'
import { AppShell } from '@/components/AppShell'
import { LoginPage } from './LoginPage'
import { TaskDetailPage } from '@/features/tasks/TaskDetailPage'
import { TasksPage } from '@/features/tasks/TasksPage'
import { OrgPage } from '@/features/org/OrgPage'
import { DeadLetterPage } from '@/features/admin/DeadLetterPage'

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

const tasks = createRoute({ getParentRoute: () => shell, path: '/tasks', component: TasksPage })
const taskDetail = createRoute({ getParentRoute: () => shell, path: '/tasks/$taskId', component: TaskDetailPage })

const failedTasks = createRoute({ getParentRoute: () => shell, path: '/failed', component: DeadLetterPage })

const routeTree = root.addChildren([login, shell.addChildren([home, tasks, taskDetail, failedTasks])])
export const router = createRouter({ routeTree, context: { queryClient: undefined! } })

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}
