import { test, expect } from '@playwright/test';
import { openApp } from './helpers';

test.describe('agent', () => {
  test('chat input and new session', async ({ page }) => {
    await openApp(page);
    await page.goto('/agent');
    await expect(page.getByTestId('chat-input')).toBeVisible({ timeout: 15000 });

    const newSessionBtn = page.getByTestId('new-session-btn');
    await newSessionBtn.scrollIntoViewIfNeeded();
    await newSessionBtn.click();

    await page.getByTestId('chat-input').fill('你好');
    await page.getByRole('button', { name: '发�? }).click();
    await expect(page.getByTestId('stream-renderer')).toBeVisible({ timeout: 15000 });
  });

  test('context panel collapses and expands', async ({ page }) => {
    await openApp(page);
    await page.goto('/agent');
    await expect(page.getByText(/当前上下�?)).toBeVisible({ timeout: 15000 });

    await page.getByTestId('context-panel-toggle').click();
    await expect(page.locator('.agent-shell--context-collapsed')).toHaveCount(1);
    await expect(page.getByText(/当前上下�?)).not.toBeVisible();

    await page.getByTestId('context-panel-toggle').click();
    await expect(page.locator('.agent-shell--context-collapsed')).toHaveCount(0);
    await expect(page.getByText(/当前上下�?)).toBeVisible();
  });
});
