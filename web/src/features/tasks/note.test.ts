import { describe, expect, it } from 'vitest'
import { taskNote } from './note'

const now = Date.parse('2026-11-26T12:00:00Z')
const later = '2026-11-26T12:30:00Z'

describe('taskNote', () => {
  it('says why a ready task waits and until when', () => {
    expect(taskNote({ status: 'ready', status_reason: 'waiting_quota', retry_at: later }, now)).toMatch(/^Waiting for model quota until /)
    expect(taskNote({ status: 'ready', status_reason: 'retry_transient', retry_at: later }, now)).toMatch(/^Retrying after a temporary provider error until /)
  })

  it('stays quiet for a ready task that is due', () => {
    expect(taskNote({ status: 'ready', status_reason: null, retry_at: null }, now)).toBeNull()
    expect(taskNote({ status: 'ready', status_reason: 'waiting_quota', retry_at: '2026-11-26T11:00:00Z' }, now)).toBeNull()
  })

  it('explains a failure that may have reached the provider', () => {
    expect(taskNote({ status: 'failed_execution', status_reason: 'call_maybe_sent', retry_at: null }, now)).toMatch(/may have reached the provider/)
  })
})
