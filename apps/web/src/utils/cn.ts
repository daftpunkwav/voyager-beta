import clsx, { type ClassValue } from 'clsx';

/** 合并 className，语义对齐 clsx */
export function cn(...inputs: ClassValue[]): string {
  return clsx(inputs);
}
