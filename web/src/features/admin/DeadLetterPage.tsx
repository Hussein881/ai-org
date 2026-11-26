import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { api, type DeadLetter } from '@/lib/api'
import { reasonText } from './reasons'

function Row({ item }: { item: DeadLetter }) {
  const qc = useQueryClient()
  const retry = useMutation({
    mutationFn: () => api.retryDeadLetter(item.id),
    onSuccess: () => {
      for (const queryKey of [['dead-letter'], ['tasks'], ['admin']]) void qc.invalidateQueries({ queryKey })
    },
  })
  return (
    <li className="flex flex-col gap-3 rounded-lg border bg-card p-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0 space-y-1">
        <Link to="/tasks/$taskId" params={{ taskId: item.id }} className="font-medium break-words underline-offset-4 hover:underline">
          {item.title}
        </Link>
        <p className="text-sm">{reasonText(item.reason)}</p>
        <p className="text-xs text-muted-foreground">
          {item.assignee}, {item.attempts} {item.attempts === 1 ? 'attempt' : 'attempts'}, last change{' '}
          {new Date(item.updated_at).toLocaleString()}
        </p>
        {retry.isError && (
          <p role="alert" className="text-sm text-destructive">
            {retry.error.message}
          </p>
        )}
      </div>
      <Button size="sm" onClick={() => retry.mutate()} disabled={retry.isPending} aria-label={`Retry ${item.title}`}>
        {retry.isPending ? 'Retrying…' : 'Retry'}
      </Button>
    </li>
  )
}

export function DeadLetterPage() {
  const q = useQuery({ queryKey: ['dead-letter'], queryFn: api.deadLetter })
  return (
    <div className="h-full space-y-4 overflow-y-auto p-4">
      <div className="space-y-1">
        <h1 className="text-lg font-semibold">Failed tasks</h1>
        <p className="text-sm text-muted-foreground">Nothing here runs again unless you retry it.</p>
      </div>
      {q.isPending && <Skeleton className="h-24 w-full" aria-label="Loading failed tasks" />}
      {q.isError && (
        <Alert variant="destructive" role="alert">
          <AlertDescription>
            Could not load failed tasks: {q.error.message}{' '}
            <Button size="sm" variant="outline" onClick={() => void q.refetch()}>
              Try again
            </Button>
          </AlertDescription>
        </Alert>
      )}
      {q.data?.length === 0 && <p className="text-muted-foreground">No failed tasks.</p>}
      {q.data && q.data.length > 0 && (
        <ul className="space-y-2">
          {q.data.map((item) => (
            <Row key={item.id} item={item} />
          ))}
        </ul>
      )}
    </div>
  )
}
