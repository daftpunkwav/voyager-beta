/** 附加根路径校验(只读/读写附加目录共用,phase-54/56):绝对路径判定,Windows 盘符(C:\ 或 C:/)、UNC(\\)、Unix(/)开头 */
export function isAbsolutePath(line: string): boolean {
  return /^[A-Za-z]:[\\/]/.test(line) || line.startsWith('\\\\') || line.startsWith('/');
}
