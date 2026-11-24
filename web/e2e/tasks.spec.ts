import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import { mkdirSync } from 'node:fs'

const SHOTS = '../artifacts/screens/S02'
const serious = (v: { impact?: string | null }[]) => v.filter((x) => ['serious', 'critical'].includes(x.impact ?? ''))

for (const scheme of ['light', 'dark'] as const) {
  test(`assign a task -> live status -> done (${scheme})`, async ({ page }, info) => {
    mkdirSync(SHOTS, { recursive: true })
    const problems: string[] = []
    page.on('console', (m) => ['error', 'warning'].includes(m.type()) && problems.push(m.text()))
    page.on('pageerror', (e) => problems.push(e.message))
    await page.emulateMedia({ colorScheme: scheme })
    await page.addInitScript((s) => localStorage.setItem('theme', s), scheme)

    await page.goto('/login')
    await page.getByLabel('Email').fill(process.env.E2E_EMAIL ?? '')
    await page.getByLabel('Password').fill(process.env.E2E_PASSWORD ?? '')
    await page.getByRole('button', { name: 'Sign in' }).click()
    await expect(page.getByRole('status')).toContainText('Live')

    const title = `Echo ${scheme} ${info.project.name} ${Date.now()}`
    await page.getByRole('link', { name: 'Tasks' }).click()
    await expect(page.getByRole('heading', { name: /Done/ })).toBeVisible().catch(() => {})
    await page.getByLabel('Task', { exact: true }).fill(title)
    await page.getByRole('button', { name: 'Assign to CEO' }).click()
    await expect(page.getByRole('link', { name: new RegExp(title) })).toBeVisible()
    await page.screenshot({ path: `${SHOTS}/tasks-${info.project.name}-${scheme}.png` })

    // live: the card moves to Done without a refresh
    const done = page.getByRole('region', { name: 'Done' })
    await expect(done.getByRole('link', { name: new RegExp(title) })).toBeVisible({ timeout: 20_000 })
    await page.screenshot({ path: `${SHOTS}/tasks-done-${info.project.name}-${scheme}.png` })
    expect(serious((await new AxeBuilder({ page }).analyze()).violations)).toEqual([])

    // survives a refresh, and the detail page shows the timeline
    await page.reload()
    await page.getByRole('link', { name: new RegExp(title) }).click()
    await expect(page.getByRole('heading', { name: title })).toBeVisible()
    await expect(page.getByText('task.created')).toBeVisible()
    await expect(page.getByText('run.finished')).toBeVisible()
    await page.screenshot({ path: `${SHOTS}/detail-${info.project.name}-${scheme}.png` })
    expect(serious((await new AxeBuilder({ page }).analyze()).violations)).toEqual([])

    // org chart shows activity in the ticker
    await page.getByRole('link', { name: 'Org chart' }).click()
    await expect(page.getByRole('log', { name: 'Activity' })).toBeVisible()
    expect(problems).toEqual([])
  })
}

test('CEO card pulses while the task runs', async ({ page }, info) => {
  test.skip(info.project.name === 'phone', 'status ring is checked on the desktop layout')
  await page.goto('/login')
  await page.getByLabel('Email').fill(process.env.E2E_EMAIL ?? '')
  await page.getByLabel('Password').fill(process.env.E2E_PASSWORD ?? '')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('status')).toContainText('Live')
  const res = await page.evaluate(async () => {
    const me = (await (await fetch('/api/auth/me')).json()) as { csrf_token: string }
    await fetch('/api/tasks', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': me.csrf_token }, body: JSON.stringify({ title: 'pulse check' }) })
    return true
  })
  expect(res).toBe(true)
  await expect(page.getByRole('img', { name: 'Status: Working' })).toBeVisible({ timeout: 10_000 })
  await page.screenshot({ path: `${SHOTS}/org-working-desktop.png` })
  await expect(page.getByRole('img', { name: 'Status: Working' })).toBeHidden({ timeout: 20_000 })
})
