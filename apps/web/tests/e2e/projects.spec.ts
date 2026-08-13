import { test, expect } from '@playwright/test';
import { openApp } from './helpers';

test.describe('projects', () => {
  test('shows project table', async ({ page }) => {
    await openApp(page);
    await page.goto('/projects');
    await expect(page.getByTestId('project-table')).toBeVisible({ timeout: 15000 });
    await expect(page.getByTestId('import-stars-btn')).toBeVisible();
  });
});
