import ELK from 'elkjs/lib/elk.bundled.js'
import type { Edge, Node } from '@xyflow/react'
import type { Role } from '@/lib/api'

export const NODE_W = 220
export const NODE_H = 96
const elk = new ELK()

export type CardData = { role: Role; onOpen?: (slug: string) => void } | { founder: true }

export function buildGraph(roles: Role[]): { nodes: Node<CardData>[]; edges: Edge[] } {
  const slugs = new Set(roles.map((r) => r.slug))
  const nodes: Node<CardData>[] = [
    { id: 'founder', type: 'founder', position: { x: 0, y: 0 }, data: { founder: true } },
    ...roles.map((role) => ({ id: role.slug, type: 'role', position: { x: 0, y: 0 }, data: { role } })),
  ]
  const edges: Edge[] = roles.map((r) => {
    const source = r.reports_to === 'founder' || !slugs.has(r.reports_to) ? 'founder' : r.reports_to
    return { id: `${source}->${r.slug}`, source, target: r.slug, type: 'smoothstep' }
  })
  return { nodes, edges }
}

export async function layout(nodes: Node<CardData>[], edges: Edge[]): Promise<Node<CardData>[]> {
  const res = await elk.layout({
    id: 'root',
    layoutOptions: {
      'elk.algorithm': 'layered',
      'elk.direction': 'DOWN',
      'elk.spacing.nodeNode': '32',
      'elk.layered.nodePlacement.bk.fixedAlignment': 'BALANCED',
      'elk.layered.spacing.nodeNodeBetweenLayers': '56',
    },
    children: nodes.map((n) => ({ id: n.id, width: NODE_W, height: NODE_H })),
    edges: edges.map((e) => ({ id: e.id, sources: [e.source], targets: [e.target] })),
  })
  const pos = new Map((res.children ?? []).map((c) => [c.id, { x: c.x ?? 0, y: c.y ?? 0 }]))
  return nodes.map((n) => ({ ...n, position: pos.get(n.id) ?? n.position }))
}
