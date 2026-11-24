import { Handle, Position, type NodeProps } from '@xyflow/react'
import { Badge } from '@/components/ui/badge'
import type { Role } from '@/lib/api'
import { NODE_H, NODE_W } from './layout'
import { statusOf } from './status'

export function StatusRing({ status }: { status: string }) {
  const s = statusOf(status)
  return (
    <span
      role="img"
      aria-label={`Status: ${s.label}`}
      className={`inline-block size-3 shrink-0 rounded-full border-[3px] ${s.ring} ${status === 'working' ? 'animate-pulse' : ''}`}
    />
  )
}

export function RoleCardBody({ role }: { role: Role }) {
  return (
    <>
      <div className="flex items-center gap-2">
        <StatusRing status={role.status} />
        <span className="truncate font-medium">{role.name}</span>
      </div>
      <Badge variant="secondary" className="mt-2 max-w-full truncate">
        {role.model} · {role.provider}
      </Badge>
      <p className="mt-1 text-xs text-muted-foreground">{statusOf(role.status).label}</p>
    </>
  )
}

export function RoleNode({ data }: NodeProps) {
  const { role, onOpen } = data as { role: Role; onOpen?: (slug: string) => void }
  return (
    <button
      type="button"
      onClick={() => onOpen?.(role.slug)}
      style={{ width: NODE_W, height: NODE_H }}
      className="rounded-xl border bg-card p-3 text-left text-card-foreground shadow-sm transition-colors hover:border-primary focus-visible:outline-2 focus-visible:outline-ring"
    >
      <Handle type="target" position={Position.Top} className="!opacity-0" />
      <RoleCardBody role={role} />
      <Handle type="source" position={Position.Bottom} className="!opacity-0" />
    </button>
  )
}

export function FounderNode() {
  return (
    <div
      style={{ width: NODE_W, height: NODE_H }}
      className="grid place-items-center rounded-xl border-2 border-primary bg-primary text-primary-foreground"
    >
      <span className="font-semibold">Founder</span>
      <Handle type="source" position={Position.Bottom} className="!opacity-0" />
    </div>
  )
}
