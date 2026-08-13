import { test, expect } from '@playwright/test';
import { openApp } from './helpers';

test.describe('graph', () => {
  test('renders force graph svg', async ({ page }) => {
    await openApp(page);
    await page.goto('/graph');
    await expect(page.getByTestId('force-graph-svg')).toBeVisible({ timeout: 15000 });
    await expect(page.getByTestId('graph-node').first()).toBeVisible();
  });
});
