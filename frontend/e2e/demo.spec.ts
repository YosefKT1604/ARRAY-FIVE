import { expect, test } from '@playwright/test'

// The main demo, start to finish, in mock mode (no backend needed).
test('main demo: report -> impact -> plans -> edit -> discard -> approve -> log -> drafts', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByText('Demo data (mock)')).toBeVisible()

  // Report
  await page.getByRole('link', { name: 'Report a problem' }).first().click()
  await page.getByRole('button', { name: 'Use the demo message' }).click()
  await page.getByRole('button', { name: 'Read message' }).click()
  await page.getByRole('button', { name: 'Report and check impact' }).click()

  // Impact
  await expect(page.getByRole('heading', { name: 'What this affects' })).toBeVisible()
  await page.getByRole('button', { name: 'See recovery options' }).click()

  // Plans: three options, recommended one first
  await expect(page.getByText('Checked: works with known data').first()).toBeVisible()
  await expect(page.getByText("Won't work").first()).toBeVisible()
  await expect(page.getByText('Needs confirmation').first()).toBeVisible()
  await page.getByRole('link', { name: 'Review this plan' }).first().click()

  // Edit 20 -> 10 shows "short 10" and the title follows the edit
  await page.getByRole('button', { name: 'Edit', exact: true }).click()
  await page.locator('input[type=number]').fill('10')
  await page.getByRole('button', { name: 'Save and re-check' }).click()
  await expect(page.getByText(/short 10/).first()).toBeVisible()
  await expect(page.getByRole('heading', { level: 1 })).toContainText('10 chairs')
  await expect(page.getByRole('button', { name: /^Approve/ })).toBeDisabled()

  // Discard goes back to version 1
  await page.getByRole('button', { name: /Discard demo edit/ }).click()
  await expect(page.getByTestId('version-note')).toContainText('version 1')

  // Approve
  await page.getByRole('button', { name: 'Approve plan' }).click()
  await expect(page.getByTestId('approved-box')).toContainText('Approved by Nurul')
  await expect(page.getByTestId('approved-box')).toContainText('Nothing has been sent')

  // Activity log
  await page.getByRole('link', { name: 'View activity log' }).click()
  await expect(page.getByText(/Nurul approved version 1 of/)).toBeVisible()

  // Drafts
  await page.goBack()
  await page.getByRole('link', { name: 'Prepare messages' }).click()
  await expect(page.getByText('Draft — not sent').first()).toBeVisible()
  await expect(page.locator('mark').first()).toBeVisible()
  await page.getByRole('button', { name: 'Approve draft' }).first().click()
  await expect(page.getByText(/Draft approved/)).toBeVisible()
})
