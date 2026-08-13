import { expect, type Page } from '@playwright/test';

/** ?????????????????????? */
export async function openApp(page: Page, landingPath = '/') {
  await page.goto(landingPath);
  if (landingPath === '/' || landingPath === '') {
    await expect(page.getByTestId('overview-hero')).toBeVisible({ timeout: 15000 });
  }
}
