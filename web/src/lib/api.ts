import type { components } from '@/lib/api-types'

export type Role = components['schemas']['RoleOut']
export type RoleDetail = components['schemas']['RoleDetail']
export type Task = components['schemas']['TaskOut']
export type TaskDetail = components['schemas']['TaskDetail']
export type OrgEvent = components['schemas']['EventOut']
export type Session = components['schemas']['SessionOut']

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

let csrf = ''
export const setCsrf = (t: string) => {
  csrf = t
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = init.method ?? 'GET'
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (method !== 'GET') headers['X-CSRF-Token'] = csrf
  const res = await fetch(path, { ...init, headers: { ...headers, ...(init.headers as Record<string, string>) }, credentials: 'same-origin' })
  if (!res.ok) {
    let detail = res.statusText
    try {
      detail = ((await res.json()) as { detail?: string }).detail ?? detail
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail)
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T)
}

export const api = {
  me: () => request<Session>('/api/auth/me'),
  login: (email: string, password: string) =>
    request<Session>('/api/auth/login', {
      method: 'POST',
      headers: { 'X-Requested-With': 'aiorg' },
      body: JSON.stringify({ email, password }),
    }),
  logout: () => request<void>('/api/auth/logout', { method: 'POST' }),
  roles: () => request<Role[]>('/api/roles'),
  tasks: () => request<Task[]>('/api/tasks'),
  task: (id: string) => request<TaskDetail>(`/api/tasks/${encodeURIComponent(id)}`),
  createTask: (title: string, description: string) =>
    request<Task>('/api/tasks', { method: 'POST', body: JSON.stringify({ title, description, assignee: 'ceo' }) }),
  transition: (id: string, to: string) =>
    request<Task>(`/api/tasks/${encodeURIComponent(id)}/transition`, { method: 'POST', body: JSON.stringify({ to }) }),
  events: () => request<OrgEvent[]>('/api/events?limit=30'),
  role: (slug: string) => request<RoleDetail>(`/api/roles/${encodeURIComponent(slug)}`),
}
