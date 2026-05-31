import { test, expect } from '@playwright/test';

test.describe('My Properties Page', () => {
  test('anonymous user is prompted to sign in', async ({ page }) => {
    // Go to My Properties page
    await page.goto('/my-properties');

    // Should see title
    await expect(page.locator('h1')).toHaveText('My Properties');

    // Should see sign in prompt
    await expect(page.locator('p')).toContainText('Sign in to view your requested and saved properties');

    // Should see Sign In button
    const signInButton = page.locator('button', { hasText: 'Sign In' });
    await expect(signInButton).toBeVisible();
  });

  test('authenticated user can view requested and saved properties tabs', async ({ page }) => {
    // Note: In staging / CI environment, authenticating with Clerk
    // is performed via Clerk test credentials or a global auth setup.
    // Here we simulate the signed-in journey if credentials are provided,
    // or test tab visibility assuming mock session is loaded.

    // Go to home page and authenticate if test credentials exist
    const testEmail = process.env.TEST_USER_EMAIL || 'test@example.com';
    const testPassword = process.env.TEST_USER_PASSWORD || 'TestPassword123!';

    await page.goto('/my-properties');

    // Click sign in if present
    const signInButton = page.locator('button', { hasText: 'Sign In' });
    if (await signInButton.isVisible()) {
      await signInButton.click();
      
      // Fill Clerk sign in form if visible
      // Wait for Clerk modal or redirect
      await page.waitForTimeout(1000); 
      if (await page.locator('[name="identifier"]').isVisible()) {
        await page.fill('[name="identifier"]', testEmail);
        await page.click('button:has-text("Continue")');
        await page.waitForSelector('[name="password"]');
        await page.fill('[name="password"]', testPassword);
        await page.click('button:has-text("Continue")');
      } else if (await page.locator('[name="emailAddress"]').isVisible()) {
        await page.fill('[name="emailAddress"]', testEmail);
        await page.fill('[name="password"]', testPassword);
        await page.click('[type="submit"]');
      }
    }

    // After sign-in, we should be on My Properties page
    await expect(page).toHaveURL(/.*my-properties/);
    await expect(page.locator('h1')).toHaveText('My Properties');

    // Verify tabs exist
    const requestedTab = page.locator('#tab-requested');
    const savedTab = page.locator('#tab-saved');

    await expect(requestedTab).toBeVisible();
    await expect(savedTab).toBeVisible();

    // Requested tab should be active by default
    await expect(requestedTab).toHaveClass(/border-zinc-900/);

    // Switch to Saved tab
    await savedTab.click();
    await expect(savedTab).toHaveClass(/border-zinc-900/);
    await expect(requestedTab).not.toHaveClass(/border-zinc-900/);

    // Switch back to Requested tab
    await requestedTab.click();
    await expect(requestedTab).toHaveClass(/border-zinc-900/);
  });
});
