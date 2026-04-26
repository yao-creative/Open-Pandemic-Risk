import { expect, test } from '@playwright/test'

test('live pipeline happy path runs to completion and renders report', async ({ page }) => {
  await page.goto('/')

  const runButton = page.locator('#run-pipeline')
  await expect(runButton).toBeVisible()
  await runButton.click()

  const statusPanel = page.locator('#status-panel')
  await expect(statusPanel).toContainText(/Run #\d+ - (queued|running)|Run #\d+ queued/)

  // Frontend polls every 2.5s; allow enough time for live ingest + enrich + score + recommend.
  await expect(statusPanel).toContainText(/Run #\d+ - completed/, { timeout: 180_000 })

  for (const stage of ['ingest_snapshot', 'enrich_snapshot_agent', 'score_snapshot', 'recommend_response_agent']) {
    await expect(page.locator(`#status-panel tr:has-text("${stage}")`)).toContainText('completed')
  }

  const reportPanel = page.locator('#report-panel')
  await expect(reportPanel).toContainText('Consolidated Report')
  await expect(reportPanel).toContainText('Risk Analytics')
  await expect(reportPanel).toContainText('Recommendation')
})
