import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from '@tanstack/react-router'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { api } from '@/lib/api'
import { statusLabel } from './TasksPage'

export function TaskDetailPage() {
  const { taskId } = useParams({ from: '/shell/tasks/$taskId' })
  const q = useQuery({ queryKey: ['task', taskId], queryFn: () => api.task(taskId) })
  return (
    <div className="h-full space-y-4 overflow-y-auto p-4">
      <Link to="/tasks" className="text-sm text-primary underline-offset-4 hover:underline">Back to tasks</Link>
      {q.isPending && <Skeleton className="h-40 w-full" />}
      {q.isError && (
        <Alert variant="destructive" role="alert">
          <AlertDescription>Could not load this task: {q.error.message}</AlertDescription>
        </Alert>
      )}
      {q.data && (
        <>
          <div>
            <h1 className="text-xl font-semibold tracking-tight">{q.data.title}</h1>
            <p className="mt-1 flex items-center gap-2 text-sm text-muted-foreground">
              <Badge>{statusLabel(q.data.status)}</Badge> assigned to {q.data.assignee}
            </p>
            {q.data.description && <p className="mt-2 text-sm">{q.data.description}</p>}
          </div>
          <section aria-label="Timeline">
            <h2 className="mb-2 text-sm font-medium">Timeline</h2>
            <ol className="space-y-1 border-l pl-4 text-sm">
              {q.data.events.map((e) => (
                <li key={e.seq}>
                  <span className="font-medium">{e.kind}</span>{' '}
                  <span className="text-muted-foreground">
                    {e.actor} · {new Date(e.created_at).toLocaleTimeString()}
                  </span>
                </li>
              ))}
            </ol>
          </section>
        </>
      )}
    </div>
  )
}
