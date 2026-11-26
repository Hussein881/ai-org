import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { api, type AdminStatus } from '@/lib/api'

export const adminQuery = { queryKey: ['admin'], queryFn: () => api.adminStatus(), refetchInterval: 5_000 }

export function workerState(s: AdminStatus | undefined, failed: boolean) {
  if (failed || !s) return { label: failed ? 'Worker unknown' : 'Checking worker', dot: 'bg-status-waiting' }
  if (s.stopped) return { label: 'Work stopped', dot: 'bg-status-blocked' }
  if (!s.worker_alive) return { label: 'Worker offline', dot: 'bg-status-blocked' }
  return { label: 'Worker alive', dot: 'bg-status-ok' }
}

function WorkerDot({ status, failed }: { status: AdminStatus | undefined; failed: boolean }) {
  const { label, dot } = workerState(status, failed)
  return (
    <span role="img" aria-label={label} title={status?.stop_reason ?? label} className="flex items-center gap-1.5 text-xs text-muted-foreground" data-testid="worker-state">
      <span className={`size-2 rounded-full ${dot}`} aria-hidden />
      <span className="hidden md:inline">{label}</span>
    </span>
  )
}

export function WorkerControls() {
  const qc = useQueryClient()
  const q = useQuery(adminQuery)
  const [open, setOpen] = useState(false)
  const [reason, setReason] = useState('')
  const refresh = (next: AdminStatus) => {
    qc.setQueryData(['admin'], next)
    void qc.invalidateQueries({ queryKey: ['tasks'] })
  }
  const stop = useMutation({
    mutationFn: () => api.stop(reason.trim()),
    onSuccess: (next) => {
      refresh(next)
      setOpen(false)
      setReason('')
    },
  })
  const resume = useMutation({ mutationFn: api.resume, onSuccess: refresh })
  const stopped = q.data?.stopped ?? false
  return (
    <>
      <WorkerDot status={q.data} failed={q.isError} />
      {stopped ? (
        <Button size="sm" onClick={() => resume.mutate()} disabled={resume.isPending}>
          {resume.isPending ? 'Resuming…' : 'Resume work'}
        </Button>
      ) : (
        <Button variant="destructive" size="sm" onClick={() => setOpen(true)}>
          <span>
            Stop<span className="hidden sm:inline"> everything</span>
          </span>
        </Button>
      )}
      {resume.isError && (
        <span role="alert" className="text-xs text-destructive">
          {resume.error.message}
        </span>
      )}
      <AlertDialog
        open={open}
        onOpenChange={(next) => {
          setOpen(next)
          if (!next) stop.reset()
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Stop everything?</AlertDialogTitle>
            <AlertDialogDescription>
              Running tasks are cancelled and cannot be restarted. Waiting tasks stay in the queue until you resume.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <div className="space-y-2">
            <Label htmlFor="stop-reason">Reason (optional)</Label>
            <Input id="stop-reason" maxLength={160} value={reason} onChange={(e) => setReason(e.target.value)} />
            {stop.isError && (
              <p role="alert" className="text-sm text-destructive">
                {stop.error.message}
              </p>
            )}
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep working</AlertDialogCancel>
            <Button variant="destructive" onClick={() => stop.mutate()} disabled={stop.isPending}>
              {stop.isPending ? 'Stopping…' : 'Stop everything'}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
