/** 摩尔斯码表（小写） */
const MORSE: Record<string, string> = {
  d: '-..',
  a: '.-',
  f: '..-.',
  t: '-',
  p: '.--.',
  u: '..-',
  n: '-.',
  k: '-.-',
};

/** 点 = 0（低跳），划 = 1（高跳） */
function encodeWord(word: string): (0 | 1)[] {
  const bits: (0 | 1)[] = [];
  for (const ch of word) {
    const pattern = MORSE[ch];
    if (!pattern) continue;
    if (bits.length > 0) bits.push(0);
    for (const symbol of pattern) {
      bits.push(symbol === '-' ? 1 : 0);
    }
  }
  return bits;
}

/** Hero 背景字母循环播放的摩尔斯比特流：daftpunk */
export const HERO_MORSE_BITS = encodeWord('daftpunk');

/** 每个字母位点的低/高跳幅度（px），制造差异感 */
const LOW_HOP_BY_LETTER = [6, 8, 5, 7, 6, 9, 5, 7, 6];
const HIGH_HOP_BY_LETTER = [17, 20, 15, 22, 18, 21, 16, 23, 19];

/** @param invert 奇数轮反转高低，使每轮视觉不尽相同 */
export function getMorseHopPx(letterIndex: number, bit: 0 | 1, invert: boolean): number {
  const isHigh = invert ? bit === 0 : bit === 1;
  const table = isHigh ? HIGH_HOP_BY_LETTER : LOW_HOP_BY_LETTER;
  return table[letterIndex % table.length] ?? (isHigh ? 18 : 7);
}

export const HERO_MORSE_INTERVAL_MS = 1618;
