import { useQuery } from '@tanstack/react-query'
import { Background, Controls, MiniMap, ReactFlow, type Node } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { useEffect, useMemo, useState } from 'react'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useLive } from '@/features/live/LiveContext'
import { api } from '@/lib/api'
import { buildGraph, layout, type CardData } from './layout'
import { FounderNode, RoleCardBody, RoleNode } from './RoleCard'
import { RoleDrawer } from './RoleDrawer'

const nodeTypes = { role: RoleNode, founder: FounderNode }

function Ticker({ events }: { events: ReturnType<typeof useLive>['ticker'] }) {
  const recent = events.slice(-3).reverse()
  return (
    <div role="log" aria-label="Activity" aria-live="polite" className="flex h-10 items-center gap-4 overflow-hidden border-t px-4 text-xs text-muted-foreground max-md:fixed max-md:inset-x-0 max-md:bottom-0 max-md:bg-background">
      {recent.length === 0 ? <span>No activity yet. Assign a task to the CEO to see it here.</span> : recent.map((e) => (
        <span key={e.seq} className="truncate">{e.kind} · {e.actor}</span>
      ))}
    </div>
  )
}

export function OrgPage() {
  const roles = useQuery({ queryKey: ['roles'], queryFn: api.roles })
  const [selected, setSelected] = useState<string | null>(null)
  const [laidOut, setLaidOut] = useState<Node<CardData>[]>([])
  const { ticker, pulses } = useLive()
  const graph = useMemo(() => buildGraph(roles.data ?? []), [roles.data])
  useEffect(() => {
    if (!roles.data?.length) return
    let live = true
    void layout(graph.nodes, graph.edges).then((n) => live && setLaidOut(n))
    return () => {
      live = false
    }
  }, [graph, roles.data])

  const nodes = useMemo(
    () => laidOut.map((n) => (n.type === 'role' ? { ...n, data: { ...n.data, onOpen: setSelected } } : n)),
    [laidOut],
  )

  const edges = useMemo(
    () => graph.edges.map((e) => ({ ...e, animated: pulses.some((p) => p.edge === e.id && p.until > Date.now()) })),
    [graph.edges, pulses],
  )

  if (roles.isPending) return <Skeleton className="m-4 h-64" />
  if (roles.isError)
    return (
      <div className="p-4">
        <Alert variant="destructive" role="alert">
          <AlertDescription>
            Could not load the organization: {roles.error.message}{' '}
            <Button size="sm" variant="outline" onClick={() => void roles.refetch()}>
              Try again
            </Button>
          </AlertDescription>
        </Alert>
      </div>
    )
  if (!roles.data.length)
    return <p className="p-6 text-muted-foreground">No roles yet. Add role cards to roles/ and restart the API.</p>

  return (
    <>
      {/* Phone and screen-reader friendly list of the same data. */}
      <ul aria-label="Roles" className="space-y-2 overflow-y-auto p-4 pb-14 md:hidden">
        {roles.data.map((r) => (
          <li key={r.slug}>
            <button
              type="button"
              onClick={() => setSelected(r.slug)}
              className="w-full rounded-xl border bg-card p-3 text-left"
            >
              <RoleCardBody role={r} />
              <span className="sr-only">Open role card</span>
            </button>
          </li>
        ))}
      </ul>
      <div className="hidden h-[calc(100%-2.5rem)] md:block" data-testid="org-chart">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          fitView
          nodesDraggable={false}
          nodesConnectable={false}
          minZoom={0.3}
        >
          <Background />
          <Controls showInteractive={false} />
          <MiniMap pannable zoomable ariaLabel="Organization minimap" />
        </ReactFlow>
      </div>
      <Ticker events={ticker} />
      <RoleDrawer slug={selected} onClose={() => setSelected(null)} />
    </>
  )
}
