import { test, expect } from '@playwright/test';
import { openApp } from './helpers';

test.describe('local single-user', () => {
  test('app opens without login page', async ({ page }) => {
    await openApp(page);
    await expect(page).toHaveURL('/');
    await expect(page.getByTestId('overview-hero')).toBeVisible();
  });

  test('login route redirects to home', async ({ page }) => {
    await page.goto('/login');
    await expect(page).toHaveURL('/');
  });
});
