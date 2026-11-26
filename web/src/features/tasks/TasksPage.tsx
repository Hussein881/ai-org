import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { useState } from 'react'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { api, type Task } from '@/lib/api'
import { taskNote } from './note'

const COLUMNS: { title: string; statuses: string[] }[] = [
  { title: 'Ready', statuses: ['draft', 'ready'] },
  { title: 'Running', statuses: ['running', 'verifying'] },
  { title: 'Needs attention', statuses: ['blocked', 'awaiting_approval', 'awaiting_info', 'failed_qa', 'failed_execution'] },
  { title: 'Done', statuses: ['completed', 'cancelled'] },
]

export const statusLabel = (s: string) => s.replace(/_/g, ' ')

function TaskForm() {
  const qc = useQueryClient()
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const create = useMutation({
    mutationFn: () => api.createTask(title.trim(), description),
    onSuccess: () => {
      setTitle('')
      setDescription('')
      void qc.invalidateQueries({ queryKey: ['tasks'] })
    },
  })
  return (
    <form
      className="grid gap-3 rounded-xl border bg-card p-4 md:grid-cols-[1fr_1fr_auto] md:items-end"
      onSubmit={(e) => {
        e.preventDefault()
        create.mutate()
      }}
    >
      <div className="space-y-2">
        <Label htmlFor="task-title">Task</Label>
        <Input id="task-title" required maxLength={200} value={title} onChange={(e) => setTitle(e.target.value)} placeholder="What should the CEO get done?" />
      </div>
      <div className="space-y-2">
        <Label htmlFor="task-desc">Details (optional)</Label>
        <Input id="task-desc" value={description} onChange={(e) => setDescription(e.target.value)} />
      </div>
      <Button type="submit" disabled={create.isPending || !title.trim()}>
        {create.isPending ? 'Assigning…' : 'Assign to CEO'}
      </Button>
      {create.isError && (
        <Alert variant="destructive" role="alert" className="md:col-span-3">
          <AlertDescription>{create.error.message}</AlertDescription>
        </Alert>
      )}
    </form>
  )
}

function TaskCard({ task }: { task: Task }) {
  const note = taskNote(task)
  return (
    <li>
      <Link to="/tasks/$taskId" params={{ taskId: task.id }} className="block rounded-lg border bg-card p-3 hover:border-primary focus-visible:outline-2 focus-visible:outline-ring">
        <span className="font-medium">{task.title}</span>
        <span className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
          <Badge variant="secondary">{statusLabel(task.status)}</Badge>
          {task.assignee}
        </span>
        {note && <span className="mt-1 block text-xs text-muted-foreground">{note}</span>}
      </Link>
    </li>
  )
}

export function TasksPage() {
  const tasks = useQuery({ queryKey: ['tasks'], queryFn: api.tasks })
  return (
    <div className="h-full space-y-4 overflow-y-auto p-4">
      <TaskForm />
      {tasks.isPending && <Skeleton className="h-40 w-full" />}
      {tasks.isError && (
        <Alert variant="destructive" role="alert">
          <AlertDescription>
            Could not load tasks: {tasks.error.message}{' '}
            <Button size="sm" variant="outline" onClick={() => void tasks.refetch()}>Try again</Button>
          </AlertDescription>
        </Alert>
      )}
      {tasks.data && tasks.data.length === 0 && (
        <p className="text-muted-foreground">No tasks yet. Assign one to the CEO above and watch it move across the board.</p>
      )}
      {tasks.data && tasks.data.length > 0 && (
        <div className="grid gap-4 md:grid-cols-4">
          {COLUMNS.map((col) => {
            const items = tasks.data.filter((t) => col.statuses.includes(t.status))
            return (
              <section key={col.title} aria-label={col.title}>
                <h2 className="mb-2 text-sm font-medium">
                  {col.title} <span className="text-muted-foreground">({items.length})</span>
                </h2>
                <ul className="space-y-2">{items.map((t) => <TaskCard key={t.id} task={t} />)}</ul>
              </section>
            )
          })}
        </div>
      )}
    </div>
  )
}
