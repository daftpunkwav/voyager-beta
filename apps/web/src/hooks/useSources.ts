/** 资源库(统一资源流)数据钩子:list_sources / 文档 / 网页剪藏 / 上传组合流。
 *
 * 事件刷新:订阅 source.added / source.ready / source.removed / task.progress,
 * 失败或变更时 invalidate 对应 query(导入/解析进度无需手动刷新)。
 */

import { useEffect } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getApi } from '@/api/client';
import { subscribe } from '@/bridge/stream';

/** 统一资源摘要(list_sources 返回;跨类型同形状,后端标注 kind)。 */
export interface SourceSummary {
  id: string;
  kind: 'repo' | 'doc' | 'web';
  title: string;
  subtitle: string;
  status: 'importing' | 'parsing' | 'ready' | 'stored' | 'failed' | string;
  progress: string;
  tags: string[];
  category: string;
  added_ts: number;
  updated_ts: number;
  match?: { section_no: number; snippet: string };
}

export interface SourceStats {
  repo: number;
  doc: number;
  web: number;
  importing: number;
  failed: number;
}

const SOURCES_KEYS = ['sourcesStream', 'sourcesStats', 'documents', 'webpages'] as const;

export function useSourceStream(params: {
  kind?: string;
  query?: string;
  status?: string;
} = {}) {
  return useQuery({
    queryKey: ['sourcesStream', params.kind ?? '', params.query ?? '', params.status ?? ''],
    queryFn: async () => {
      const res = await getApi().listSources(params);
      return (res.data ?? []) as SourceSummary[];
    },
  });
}

export function useSourcesStats() {
  return useQuery({
    queryKey: ['sourcesStats'],
    queryFn: async () => {
      const res = await getApi().sourcesStats();
      return res.data as SourceStats;
    },
  });
}

/** source.* 事件 → 刷新资源流(导入/解析进度实时可见,无需轮询)。 */
export function useSourceEvents() {
  const qc = useQueryClient();
  useEffect(() => {
    const off = subscribe(
      ['source.added', 'source.ready', 'source.removed', 'task.failed'],
      () => {
        for (const key of SOURCES_KEYS) {
          void qc.invalidateQueries({ queryKey: [key] });
        }
      },
    );
    return off;
  }, [qc]);
}

// ---------- 文档 ----------

export interface DocumentDetail {
  id: string;
  title: string;
  filename: string;
  ext: string;
  status: string;
  error: string;
  category: string;
  tags: string[];
  progress: string;
  note: string;
  local_path: string;
  sections: { section_no: number; title: string; page_start: number; page_end: number }[];
  total_sections: number;
}

export function useDocument(docId: string | undefined) {
  return useQuery({
    queryKey: ['documents', docId],
    queryFn: async () => {
      if (!docId) throw new Error('missing doc id');
      const res = await getApi().getDocument(docId);
      return res.data as DocumentDetail;
    },
    enabled: Boolean(docId),
  });
}

/** 解析进度事件:文档解析中/task.failed 时刷新详情(status/error 实时更新)。 */
export function useDocumentEvents(docId: string | undefined) {
  const qc = useQueryClient();
  useEffect(() => {
    if (!docId) return;
    const off = subscribe(['task.progress', 'task.failed', 'source.ready'], (e) => {
      if (e.payload.source_id === docId) {
        void qc.invalidateQueries({ queryKey: ['documents', docId] });
      }
    });
    return off;
  }, [qc, docId]);
}

export function useDocSection(docId: string | undefined, sectionNo: number | undefined) {
  return useQuery({
    queryKey: ['docSection', docId, sectionNo],
    queryFn: async () => {
      if (!docId || !sectionNo) throw new Error('missing doc id or section no');
      const res = await getApi().getDocSection(docId, sectionNo);
      return res.data as { section_no: number; title: string; page_start: number; page_end: number; text: string; total_sections: number };
    },
    enabled: Boolean(docId) && Boolean(sectionNo),
  });
}

export function useRemoveDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (docId: string) => {
      await getApi().removeDocument(docId);
    },
    onSuccess: () => {
      for (const key of SOURCES_KEYS) {
        void qc.invalidateQueries({ queryKey: [key] });
      }
    },
  });
}

export function useSetDocumentMeta() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: { docId: string; meta: { title?: string; category?: string; tags?: string[]; progress?: string; note?: string } }) => {
      await getApi().setDocumentMeta(input.docId, input.meta);
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['documents'] });
      void qc.invalidateQueries({ queryKey: ['sourcesStream'] });
    },
  });
}

// ---------- 网页剪藏 ----------

export interface WebPage {
  id: string;
  title: string;
  url: string;
  domain: string;
  summary: string;
  content: string;
  tags: string[];
  meta: { images?: string[]; chars?: number };
}

export function useWebPage(pageId: string | undefined) {
  return useQuery({
    queryKey: ['webpages', pageId],
    queryFn: async () => {
      if (!pageId) throw new Error('missing page id');
      const res = await getApi().getPage(pageId);
      return res.data as WebPage;
    },
    enabled: Boolean(pageId),
  });
}

export function useSaveUrl() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: { url: string; title?: string; tags?: string[] }) => {
      await getApi().saveUrl(input.url, input);
    },
    onSuccess: () => {
      for (const key of SOURCES_KEYS) {
        void qc.invalidateQueries({ queryKey: [key] });
      }
    },
  });
}

export function useRemovePage() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (pageId: string) => {
      await getApi().removePage(pageId);
    },
    onSuccess: () => {
      for (const key of SOURCES_KEYS) {
        void qc.invalidateQueries({ queryKey: [key] });
      }
    },
  });
}

export function useSetPageMeta() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: { pageId: string; meta: { title?: string; tags?: string[]; category?: string } }) => {
      await getApi().setPageMeta(input.pageId, input.meta);
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['webpages'] });
      void qc.invalidateQueries({ queryKey: ['sourcesStream'] });
    },
  });
}
