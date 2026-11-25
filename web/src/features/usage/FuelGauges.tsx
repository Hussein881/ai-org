import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Skeleton } from '@/components/ui/skeleton'
import { api, type ProviderGauge } from '@/lib/api'

const STATUS_TEXT: Record<string, string> = {
  ok: 'OK',
  warn: 'Running low',
  exhausted: 'Used up',
  blocked: 'Paused by provider',
  disabled: 'Disabled',
}
const BAR: Record<string, string> = {
  ok: '[&_[data-slot=progress-indicator]]:bg-primary',
  warn: '[&_[data-slot=progress-indicator]]:bg-status-waiting',
  exhausted: '[&_[data-slot=progress-indicator]]:bg-status-blocked',
  blocked: '[&_[data-slot=progress-indicator]]:bg-status-blocked',
  disabled: '[&_[data-slot=progress-indicator]]:bg-muted-foreground',
}

const fmt = (unit: string, n: number) => (unit === 'usd' ? `$${n.toFixed(2)}` : String(Math.round(n)))
const windowLabel = (w: string) => (w === '5h' ? 'per 5 hours' : w === 'day' ? 'today' : 'this month')
const resetText = (iso: string | null) =>
  iso
    ? `resets ${new Date(iso).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}`
    : 'no calls yet'
const pctOf = (used: number, limit: number) => (limit ? Math.min(100, (100 * used) / limit) : 0)

/** The limit that matters most for the pill: the busiest one. */
export function primaryLimit(p: ProviderGauge) {
  return [...p.limits].sort((a, b) => b.used / (b.limit || 1) - a.used / (a.limit || 1))[0]
}

export function describe(p: ProviderGauge): string {
  const l = primaryLimit(p)
  if (!p.enabled) return `${p.label}: disabled by policy`
  if (!l) return `${p.label}: no limit set`
  const unit = l.unit === 'usd' ? '' : ' calls'
  return `${p.label}: ${fmt(l.unit, l.used)} of ${fmt(l.unit, l.limit)}${unit} ${windowLabel(l.window)}, ${STATUS_TEXT[p.status]?.toLowerCase()}, ${resetText(l.resets_at)}`
}

function Pill({ p, onOpen }: { p: ProviderGauge; onOpen: () => void }) {
  const l = primaryLimit(p)
  return (
    <button
      type="button"
      onClick={onOpen}
      aria-label={describe(p)}
      className="flex w-24 flex-col gap-1 rounded-md px-1.5 py-1 text-left text-xs hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring"
    >
      <span className="truncate text-muted-foreground" aria-hidden>
        {p.label}
      </span>
      <Progress
        value={l ? pctOf(l.used, l.limit) : 0}
        aria-label={`${p.label} usage`}
        className={BAR[p.status] ?? BAR.ok}
      />
    </button>
  )
}

function Detail({ p }: { p: ProviderGauge }) {
  return (
    <section className="space-y-2 rounded-lg border p-3" aria-label={p.label}>
      <h3 className="flex items-center justify-between text-sm font-medium">
        {p.label}
        <span className="text-xs font-normal text-muted-foreground">{STATUS_TEXT[p.status]}</span>
      </h3>
      {p.limits.length === 0 && <p className="text-xs text-muted-foreground">No limit set.</p>}
      {p.limits.map((l) => (
        <div key={`${l.window}-${l.model ?? 'all'}`} className="space-y-1 text-xs">
          <div className="flex justify-between">
            <span>
              {l.model ? `${l.model}, ` : ''}
              {windowLabel(l.window)}
              {l.hard ? '' : ' (soft limit)'}
            </span>
            <span>
              {fmt(l.unit, l.used)} / {fmt(l.unit, l.limit)}
            </span>
          </div>
          <Progress
            value={pctOf(l.used, l.limit)}
            aria-label={`${p.label} ${l.model ? `${l.model} ` : ''}${windowLabel(l.window)}`}
            className={BAR[p.status] ?? BAR.ok}
          />
          <p className="text-muted-foreground">{resetText(l.resets_at)}</p>
        </div>
      ))}
      {p.blocked_until && (
        <p className="text-xs text-status-blocked">Paused until {new Date(p.blocked_until).toLocaleTimeString()}</p>
      )}
    </section>
  )
}

export function FuelGauges() {
  const q = useQuery({ queryKey: ['usage'], queryFn: api.usage, refetchInterval: 60_000 })
  const [open, setOpen] = useState(false)

  if (q.isPending) return <Skeleton className="h-8 w-24" aria-label="Loading fuel gauges" />
  if (q.isError)
    return (
      <Button variant="outline" size="sm" onClick={() => void q.refetch()}>
        Fuel unavailable. Retry
      </Button>
    )
  const shown = q.data.providers.filter((p) => p.enabled)
  return (
    <>
      <div role="group" aria-label="Fuel gauges" className="hidden items-center gap-1 sm:flex">
        {shown.map((p) => (
          <Pill key={p.provider} p={p} onOpen={() => setOpen(true)} />
        ))}
      </div>
      <Button variant="outline" size="sm" className="sm:hidden" onClick={() => setOpen(true)}>
        Fuel
      </Button>
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent className="w-full overflow-y-auto sm:max-w-md">
          <SheetHeader>
            <SheetTitle>Fuel</SheetTitle>
            <SheetDescription>How much of each model allowance has been used.</SheetDescription>
          </SheetHeader>
          <div className="space-y-3 px-4 pb-6">
            {q.data.providers.length === 0 ? (
              <p className="text-sm text-muted-foreground">No providers configured.</p>
            ) : (
              q.data.providers.map((p) => <Detail key={p.provider} p={p} />)
            )}
          </div>
        </SheetContent>
      </Sheet>
    </>
  )
}
