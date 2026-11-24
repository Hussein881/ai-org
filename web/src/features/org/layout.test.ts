import { describe, expect, it } from 'vitest'
import type { Role } from '@/lib/api'
import { buildGraph, layout } from './layout'

const r = (slug: string, reports_to: string): Role => ({
  slug, name: slug, department: 'd', reports_to, model: 'm', provider: 'p', status: 'idle', version: 1,
})

describe('org graph', () => {
  it('links roles to their manager, defaulting to the founder', () => {
    const { nodes, edges } = buildGraph([r('ceo', 'founder'), r('dir', 'ceo'), r('x', 'missing')])
    expect(nodes.map((n) => n.id)).toEqual(['founder', 'ceo', 'dir', 'x'])
    expect(edges.map((e) => e.id)).toEqual(['founder->ceo', 'ceo->dir', 'founder->x'])
  })
  it('lays managers above reports', async () => {
    const { nodes, edges } = buildGraph([r('ceo', 'founder'), r('dir', 'ceo')])
    const out = await layout(nodes, edges)
    const y = (id: string) => out.find((n) => n.id === id)!.position.y
    expect(y('founder')).toBeLessThan(y('ceo'))
    expect(y('ceo')).toBeLessThan(y('dir'))
  })
})
