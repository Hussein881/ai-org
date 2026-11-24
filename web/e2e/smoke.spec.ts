import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import { mkdirSync } from 'node:fs'

const EMAIL = process.env.E2E_EMAIL ?? ''
const PASSWORD = process.env.E2E_PASSWORD ?? ''
const SHOTS = '../artifacts/screens/S01'

for (const scheme of ['light', 'dark'] as const) {
  test(`login -> org chart -> drawer (${scheme})`, async ({ page }, info) => {
    mkdirSync(SHOTS, { recursive: true })
    const problems: string[] = []
    page.on('console', (m) => ['error', 'warning'].includes(m.type()) && !m.text().includes('401 (Unauthorized)') && problems.push(m.text()))
    page.on('pageerror', (e) => problems.push(e.message))
    await page.emulateMedia({ colorScheme: scheme })
    await page.addInitScript((s) => localStorage.setItem('theme', s), scheme)

    // unauthenticated visit is sent to login
    await page.goto('/')
    await expect(page).toHaveURL(/\/login$/)
    await page.screenshot({ path: `${SHOTS}/login-${info.project.name}-${scheme}.png` })
    expect((await new AxeBuilder({ page }).analyze()).violations.filter((v) => ['serious', 'critical'].includes(v.impact ?? ''))).toEqual([])

    // wrong password shows an error
    await page.getByLabel('Email').fill(EMAIL)
    await page.getByLabel('Password').fill('wrong-password')
    await page.getByRole('button', { name: 'Sign in' }).click()
    await expect(page.getByRole('alert')).toContainText('Invalid')

    await page.getByLabel('Password').fill(PASSWORD)
    await page.getByRole('button', { name: 'Sign in' }).click()
    await expect(page).toHaveURL(/\/$/)

    const phone = info.project.name === 'phone'
    const card = phone
      ? page.getByRole('list', { name: 'Roles' }).getByRole('button', { name: /CEO/ })
      : page.getByRole('button', { name: /CEO/ })
    await expect(card).toBeVisible()
    // all seven roles render
    const names = ['CEO', 'Board Advisor', 'Chief of Staff', 'Engineering Director', 'Coding Workers', 'QA', 'Efficiency Assurance']
    for (const n of names) {
      await expect(
        phone ? page.getByRole('list', { name: 'Roles' }).getByText(n, { exact: true }) : page.getByRole('button', { name: new RegExp(n) }),
      ).toBeVisible()
    }
    await page.waitForTimeout(500)
    await page.screenshot({ path: `${SHOTS}/org-${info.project.name}-${scheme}.png` })
    expect((await new AxeBuilder({ page }).analyze()).violations.filter((v) => ['serious', 'critical'].includes(v.impact ?? ''))).toEqual([])

    await card.click()
    const drawer = page.getByRole('dialog')
    await expect(drawer.getByText('Responsibilities')).toBeVisible()
    await page.screenshot({ path: `${SHOTS}/drawer-${info.project.name}-${scheme}.png` })
    await page.keyboard.press('Escape')
    await expect(drawer).toBeHidden()
    expect(problems).toEqual([])
  })
}
