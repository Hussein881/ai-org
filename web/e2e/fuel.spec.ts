import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import { mkdirSync } from 'node:fs'

const SHOTS = '../artifacts/screens/S03'
const serious = (v: { impact?: string | null }[]) => v.filter((x) => ['serious', 'critical'].includes(x.impact ?? ''))

for (const scheme of ['light', 'dark'] as const) {
  test(`fuel gauges and role usage (${scheme})`, async ({ page }, info) => {
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

    const phone = info.project.name === 'phone'
    if (phone) {
      await expect(page.getByRole('button', { name: 'Fuel', exact: true })).toBeVisible()
    } else {
      const group = page.getByRole('group', { name: 'Fuel gauges' })
      // the pill shows whichever policy limit is busiest, which depends on today's traffic
      await expect(group.getByRole('button', { name: /Claude subscription: \d+ of (80 calls today|20 calls per 5 hours)/ })).toBeVisible()
      await expect(group.getByRole('button', { name: /Claude API: \$[\d.]+ of \$30\.00 this month/ })).toBeVisible()
      await expect(group.getByRole('button', { name: /Codex/ })).toBeVisible()
      await expect(group.getByRole('button', { name: /Gemini/ })).toBeVisible()
      await expect(group.getByRole('button', { name: /OpenRouter/ })).toBeVisible()
    }
    await page.screenshot({ path: `${SHOTS}/gauges-${info.project.name}-${scheme}.png` })
    expect(serious((await new AxeBuilder({ page }).analyze()).violations)).toEqual([])

    // detail sheet lists every provider, including the disabled one
    await (phone ? page.getByRole('button', { name: 'Fuel', exact: true }) : page.getByRole('group', { name: 'Fuel gauges' }).getByRole('button', { name: /Codex/ })).click()
    const sheet = page.getByRole('dialog')
    await expect(sheet.getByRole('region', { name: 'OpenAI' })).toContainText('Disabled')
    await expect(sheet.getByRole('region', { name: 'Claude API' })).toContainText('$')
    await page.waitForTimeout(600)
    await page.screenshot({ path: `${SHOTS}/gauges-open-${info.project.name}-${scheme}.png` })
    expect(serious((await new AxeBuilder({ page }).analyze()).violations)).toEqual([])
    await page.keyboard.press('Escape')
    await expect(sheet).toBeHidden()

    // role drawer shows the route and today's calls
    if (!phone) {
      await page.getByRole('button', { name: /CEO/ }).click()
      const drawer = page.getByRole('dialog')
      await expect(drawer.getByText('Calls today')).toBeVisible()
      await expect(drawer.getByText('codex_cli / default')).toBeVisible()
    }
    expect(problems).toEqual([])
  })
}
