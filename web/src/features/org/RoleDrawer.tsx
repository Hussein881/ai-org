import { useQuery } from '@tanstack/react-query'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Skeleton } from '@/components/ui/skeleton'
import { api } from '@/lib/api'
import { StatusRing } from './RoleCard'
import { statusOf } from './status'

export function RoleDrawer({ slug, onClose }: { slug: string | null; onClose: () => void }) {
  const q = useQuery({ queryKey: ['role', slug], queryFn: () => api.role(slug!), enabled: !!slug })
  return (
    <Sheet open={!!slug} onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-md">
        <SheetHeader>
          <SheetTitle>{q.data?.name ?? 'Role card'}</SheetTitle>
          <SheetDescription>{q.data?.summary ?? 'Loading role details'}</SheetDescription>
        </SheetHeader>
        <div className="space-y-4 px-4 pb-6">
          {q.isPending && <Skeleton className="h-24 w-full" />}
          {q.isError && (
            <Alert variant="destructive">
              <AlertDescription>Could not load this role: {q.error.message}</AlertDescription>
            </Alert>
          )}
          {q.data && (
            <>
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
                <dt className="text-muted-foreground">Status</dt>
                <dd className="flex items-center gap-2">
                  <StatusRing status={q.data.status} />
                  {statusOf(q.data.status).label}
                </dd>
                <dt className="text-muted-foreground">Model</dt>
                <dd>{q.data.model} · {q.data.provider}</dd>
                <dt className="text-muted-foreground">Reports to</dt>
                <dd>{q.data.reports_to}</dd>
                <dt className="text-muted-foreground">Department</dt>
                <dd>{q.data.department}</dd>
                <dt className="text-muted-foreground">Card version</dt>
                <dd>v{q.data.version}</dd>
              </dl>
              <section>
                <h3 className="mb-1 text-sm font-medium">Responsibilities</h3>
                <ul className="list-disc space-y-1 pl-5 text-sm">
                  {q.data.responsibilities.map((r) => (
                    <li key={r}>{r}</li>
                  ))}
                </ul>
              </section>
            </>
          )}
        </div>
      </SheetContent>
    </Sheet>
  )
}
