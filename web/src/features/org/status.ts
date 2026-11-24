export const STATUS: Record<string, { label: string; ring: string }> = {
  idle: { label: 'Idle', ring: 'border-status-idle' },
  working: { label: 'Working', ring: 'border-status-working' },
  waiting: { label: 'Waiting for info', ring: 'border-status-waiting' },
  blocked: { label: 'Blocked', ring: 'border-status-blocked' },
  founder: { label: 'Awaiting founder', ring: 'border-status-founder' },
}
export const statusOf = (s: string) => STATUS[s] ?? STATUS.idle!
