import type { SSEEvent, SSEEventType } from '@/api/types';

/**
 * 解析 SSE 文本流（`event: xxx\ndata: {...}\n\n` 格式）
 * 供真实后端 ReadableStream 消费使用
 *
 * @param reader  上游字节流读取器
 * @param signal  可选 AbortSignal；触发后立即停止并关闭底层 reader
 */
export async function* parseSSEStream(
  reader: ReadableStreamDefaultReader<Uint8Array>,
  signal?: AbortSignal
): AsyncGenerator<SSEEvent> {
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      if (signal?.aborted) break;
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split('\n\n');
      buffer = parts.pop() ?? '';

      for (const part of parts) {
        const event = parseSSEBlock(part);
        if (event) yield event;
        if (signal?.aborted) break;
      }
      if (signal?.aborted) break;
    }

    if (buffer.trim()) {
      const event = parseSSEBlock(buffer);
      if (event) yield event;
    }
  } finally {
    // 若被外部取消，先取消底层 reader 再释放 lock，避免资源泄漏
    if (signal?.aborted) {
      try {
        await reader.cancel();
      } catch {
        // 取消失败也忽略 — 浏览器会在流空闲时回收
      }
    }
    try {
      reader.releaseLock();
    } catch {
      // reader 已被外部释放；忽略
    }
  }
}

function parseSSEBlock(block: string): SSEEvent | null {
  let eventType: SSEEventType | null = null;
  const dataLines: string[] = [];

  for (const line of block.split('\n')) {
    if (line.startsWith('event:')) {
      eventType = line.slice(6).trim() as SSEEventType;
    } else if (line.startsWith('data:')) {
      // SSE 规范：多行 data 以 \n 拼接（字段值前可有可选空格）
      dataLines.push(line.slice(5).replace(/^\s/, ''));
    }
  }

  const dataStr = dataLines.join('\n');
  if (!eventType || !dataStr) return null;

  try {
    const data = JSON.parse(dataStr) as Record<string, unknown>;
    return { event: eventType, data };
  } catch {
    return null;
  }
}
