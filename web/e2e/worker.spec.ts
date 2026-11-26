import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'
import { mkdirSync } from 'node:fs'

const SHOTS = '../artifacts/screens/S04'
const serious = (v: { impact?: string | null }[]) => v.filter((x) => ['serious', 'critical'].includes(x.impact ?? ''))
const axe = async (page: Page) => expect(serious((await new AxeBuilder({ page }).analyze()).violations)).toEqual([])

// One stack-wide stop flag: these tests must not run in parallel with each other.
test.describe.configure({ mode: 'serial' })

for (const scheme of ['light', 'dark'] as const) {
  test(`worker dot, stop everything, resume, failed tasks (${scheme})`, async ({ page }, info) => {
    mkdirSync(SHOTS, { recursive: true })
    const problems: string[] = []
    page.on('console', (m) => ['error', 'warning'].includes(m.type()) && !m.text().includes('401 (Unauthorized)') && problems.push(m.text()))
    page.on('pageerror', (e) => problems.push(e.message))
    await page.emulateMedia({ colorScheme: scheme })
    await page.addInitScript((s) => localStorage.setItem('theme', s), scheme)
    await page.goto('/login')
    await page.getByLabel('Email').fill(process.env.E2E_EMAIL ?? '')
    await page.getByLabel('Password').fill(process.env.E2E_PASSWORD ?? '')
    await page.getByRole('button', { name: 'Sign in' }).click()
    await expect(page.getByRole('status')).toContainText('Live')
    const shot = (name: string) => page.screenshot({ path: `${SHOTS}/${name}-${info.project.name}-${scheme}.png` })

    await expect(page.getByRole('img', { name: 'Worker alive' })).toBeVisible()
    await shot('alive')
    await axe(page)
    // nothing may push the page sideways on a phone
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0)

    await page.getByRole('button', { name: /^Stop/ }).click()
    const dialog = page.getByRole('alertdialog')
    await expect(dialog).toContainText('Running tasks are cancelled')
    await dialog.getByLabel('Reason (optional)').fill('e2e check')
    await page.waitForTimeout(400)
    await shot('confirm')
    await axe(page)
    await dialog.getByRole('button', { name: 'Stop everything' }).click()
    await expect(page.getByRole('img', { name: 'Work stopped' })).toBeVisible()

    // while stopped, a new task waits
    await page.getByRole('link', { name: 'Tasks' }).click()
    const title = `held ${scheme} ${info.project.name} ${Date.now()}`
    await page.getByLabel('Task', { exact: true }).fill(title)
    await page.getByRole('button', { name: 'Assign to CEO' }).click()
    const card = page.getByRole('link', { name: new RegExp(title) })
    await expect(card).toBeVisible()
    await page.waitForTimeout(3000)
    await expect(page.getByRole('region', { name: 'Ready' })).toContainText(title)
    await shot('stopped')

    await page.getByRole('button', { name: 'Resume work' }).click()
    await expect(page.getByRole('img', { name: 'Worker alive' })).toBeVisible()
    await expect(page.getByRole('region', { name: 'Done' })).toContainText(title, { timeout: 30_000 })

    await page.getByRole('link', { name: 'Failed', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'Failed tasks' })).toBeVisible()
    await expect(page.getByText(/may or may not have gone through|No failed tasks/).first()).toBeVisible()
    await shot('failed')
    await axe(page)
    expect(problems).toEqual([])
  })
}
