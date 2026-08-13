import { describe, expect, it } from 'vitest';
import { validateGithubUrl } from '@/utils/validators';

describe('validators', () => {
  it('validateGithubUrl accepts github repo urls', () => {
    expect(
      validateGithubUrl('https://github.com/facebook/react').valid
    ).toBe(true);
    expect(validateGithubUrl('not-a-url').valid).toBe(false);
  });
});
