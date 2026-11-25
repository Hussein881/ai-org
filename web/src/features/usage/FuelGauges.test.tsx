import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, type ProviderGauge, type UsageOut } from '@/lib/api'
import { FuelGauges, describe as describeGauge } from './FuelGauges'

const claude: ProviderGauge = {
  provider: 'claude_cli', label: 'Claude subscription', enabled: true, pricing_basis: 'subscription',
  status: 'ok', blocked_until: null,
  limits: [{ window: 'day', model: null, unit: 'calls', used: 12, limit: 80, hard: true, resets_at: '2026-11-26T00:00:00Z' }],
}
const apiGauge: ProviderGauge = {
  provider: 'anthropic_api', label: 'Claude API', enabled: true, pricing_basis: 'api', status: 'warn', blocked_until: null,
  limits: [{ window: 'month', model: null, unit: 'usd', used: 24.5, limit: 30, hard: true, resets_at: null }],
}
const wrap = (ui: React.ReactElement) => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}
afterEach(() => vi.restoreAllMocks())

describe('FuelGauges', () => {
  it('shows a loading state, then accessible gauges with real numbers', async () => {
    vi.spyOn(api, 'usage').mockResolvedValue({ providers: [claude, apiGauge] } satisfies UsageOut)
    wrap(<FuelGauges />)
    expect(screen.getByLabelText('Loading fuel gauges')).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: /Claude subscription: 12 of 80 calls today, ok/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Claude API: \$24\.50 of \$30\.00 this month, running low/ })).toBeInTheDocument()
  })

  it('shows an error with a retry that refetches', async () => {
    const spy = vi.spyOn(api, 'usage').mockRejectedValueOnce(new Error('down')).mockResolvedValue({ providers: [claude] })
    wrap(<FuelGauges />)
    const retry = await screen.findByRole('button', { name: /Fuel unavailable/ })
    await userEvent.click(retry)
    await waitFor(() => expect(spy).toHaveBeenCalledTimes(2))
    expect(await screen.findByRole('button', { name: /Claude subscription/ })).toBeInTheDocument()
  })

  it('opens the detail sheet from the keyboard', async () => {
    vi.spyOn(api, 'usage').mockResolvedValue({ providers: [claude] })
    wrap(<FuelGauges />)
    const pill = await screen.findByRole('button', { name: /Claude subscription/ })
    pill.focus()
    await userEvent.keyboard('{Enter}')
    expect(await screen.findByRole('dialog')).toHaveTextContent('How much of each model allowance has been used')
    expect(screen.getByRole('dialog')).toHaveTextContent('12 / 80')
  })

  it('describes empty, disabled and limitless providers without inventing numbers', () => {
    expect(describeGauge({ ...claude, limits: [{ ...claude.limits[0]!, used: 0, resets_at: null }] })).toMatch(/0 of 80 calls today, ok, no calls yet/)
    expect(describeGauge({ ...claude, enabled: false })).toBe('Claude subscription: disabled by policy')
    expect(describeGauge({ ...claude, limits: [] })).toBe('Claude subscription: no limit set')
  })
})
