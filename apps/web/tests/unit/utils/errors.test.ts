import { describe, expect, it } from 'vitest';
import { extractErrorMessage, isApiError } from '@/utils/errors';

describe('errors', () => {
  it('isApiError returns true for ApiError shape', () => {
    expect(isApiError({ error: { code: 'X', message: 'm' } })).toBe(true);
  });

  it('isApiError returns false for plain Error', () => {
    expect(isApiError(new Error('boom'))).toBe(false);
  });

  it('isApiError returns false for null and primitives', () => {
    expect(isApiError(null)).toBe(false);
    expect(isApiError(undefined)).toBe(false);
    expect(isApiError('x')).toBe(false);
  });

  it('extractErrorMessage returns ApiError message', () => {
    expect(extractErrorMessage({ error: { code: 'X', message: '具体原因' } })).toBe(
      '具体原因',
    );
  });

  it('extractErrorMessage returns Error.message for native Error', () => {
    expect(extractErrorMessage(new Error('native'))).toBe('native');
  });

  it('extractErrorMessage returns fallback for unknown shape', () => {
    expect(extractErrorMessage({})).toBe('未知错误，请重试');
    expect(extractErrorMessage(null)).toBe('未知错误，请重试');
  });
});
