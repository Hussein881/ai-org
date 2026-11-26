import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, type AdminStatus, type DeadLetter } from '@/lib/api'
import { DeadLetterPage } from './DeadLetterPage'
import { WorkerControls, workerState } from './WorkerControls'

vi.mock('@tanstack/react-router', () => ({ Link: ({ children }: { children: React.ReactNode }) => <a href="#x">{children}</a> }))

const alive: AdminStatus = {
  worker_alive: true, heartbeat_at: '2026-11-26T00:00:00Z', in_flight: 0, stopped: false, stop_reason: null, dead_letter_count: 0,
}
const failed: DeadLetter = {
  id: '1', title: 'Draft the plan', assignee: 'ceo', reason: 'effect_unknown', attempts: 2, updated_at: '2026-11-26T00:00:00Z',
}
const wrap = (ui: React.ReactElement) => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}
afterEach(() => vi.restoreAllMocks())

describe('WorkerControls', () => {
  it('names the four worker states', () => {
    expect(workerState(alive, false).label).toBe('Worker alive')
    expect(workerState({ ...alive, worker_alive: false }, false).label).toBe('Worker offline')
    expect(workerState({ ...alive, stopped: true }, false).label).toBe('Work stopped')
    expect(workerState(undefined, true).label).toBe('Worker unknown')
    expect(workerState(alive, false).dot).toBe('bg-status-ok') // a theme token, not a raw palette class
  })

  it('only stops after the dialog is confirmed, then offers resume', async () => {
    vi.spyOn(api, 'adminStatus').mockResolvedValue(alive)
    const stop = vi.spyOn(api, 'stop').mockResolvedValue({ ...alive, stopped: true, stop_reason: 'testing' })
    wrap(<WorkerControls />)
    await screen.findByLabelText('Worker alive')
    await userEvent.click(screen.getByRole('button', { name: /Stop/ }))
    await userEvent.click(screen.getByRole('button', { name: 'Keep working' }))
    expect(stop).not.toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: /Stop/ }))
    await userEvent.type(await screen.findByLabelText('Reason (optional)'), 'testing')
    await userEvent.click(screen.getByRole('button', { name: 'Stop everything' }))
    expect(stop).toHaveBeenCalledWith('testing')
    expect(await screen.findByRole('button', { name: 'Resume work' })).toBeInTheDocument()
    expect(screen.getByLabelText('Work stopped')).toBeInTheDocument()
  })

  it('keeps the dialog open and says why when stopping fails', async () => {
    vi.spyOn(api, 'adminStatus').mockResolvedValue(alive)
    vi.spyOn(api, 'stop').mockRejectedValue(new Error('database is busy'))
    wrap(<WorkerControls />)
    await userEvent.click(await screen.findByRole('button', { name: /Stop/ }))
    await userEvent.click(await screen.findByRole('button', { name: 'Stop everything' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('database is busy')
    expect(screen.getByRole('alertdialog')).toBeInTheDocument()
  })
})

describe('DeadLetterPage', () => {
  it('shows the empty state', async () => {
    vi.spyOn(api, 'deadLetter').mockResolvedValue([])
    wrap(<DeadLetterPage />)
    expect(screen.getByLabelText('Loading failed tasks')).toBeInTheDocument()
    expect(await screen.findByText('No failed tasks.')).toBeInTheDocument()
  })

  it('explains the reason and retries', async () => {
    vi.spyOn(api, 'deadLetter').mockResolvedValueOnce([failed]).mockResolvedValue([])
    const retry = vi.spyOn(api, 'retryDeadLetter').mockResolvedValue(undefined)
    wrap(<DeadLetterPage />)
    expect(await screen.findByText(/may or may not have gone through/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Retry Draft the plan' }))
    await waitFor(() => expect(retry).toHaveBeenCalledWith('1'))
    expect(await screen.findByText('No failed tasks.')).toBeInTheDocument()
  })

  it('shows a load error with a retry', async () => {
    vi.spyOn(api, 'deadLetter').mockRejectedValue(new Error('down'))
    wrap(<DeadLetterPage />)
    expect(await screen.findByRole('alert')).toHaveTextContent('down')
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })
})
