import type { Task } from '@/lib/api'
import { reasonText } from '@/features/admin/reasons'

const WAITING: Record<string, string> = {
  waiting_quota: 'Waiting for model quota',
  retry_transient: 'Retrying after a temporary provider error',
}

/** One line under a task's status: why it waits (and until when), or why it ended as it did. */
export function taskNote(task: Pick<Task, 'status' | 'status_reason' | 'retry_at'>, now = Date.now()): string | null {
  const reason = task.status_reason ?? null
  if (task.status === 'ready') {
    if (!task.retry_at || new Date(task.retry_at).getTime() <= now) return null
    const until = new Date(task.retry_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    return `${(reason && WAITING[reason]) ?? 'Waiting'} until ${until}`
  }
  return reason ? reasonText(reason) : null
}
