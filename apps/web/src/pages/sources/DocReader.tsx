/** 文档阅读器:PDF 原版式(pdf.js 分页)与提取文本(分章)双视图。
 *
 * 用户看原版式,agent 读提取文本(§8.2);EPUB/DOCX/TXT/MD 无原版式渲染,
 * 直接展示分章文本。解析中显示进度,失败给出原因。
 */

import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useDocument, useDocSection, useDocumentEvents, useRemoveDocument, useSetDocumentMeta } from '@/hooks/useSources';
import { getApi } from '@/api/client';
import { useUIStore } from '@/stores/uiStore';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState, EmptyStateIcons } from '@/components/common/EmptyState';
import { MarkdownRenderer } from '@/components/common/MarkdownRenderer';
import { TagEditor } from './TagEditor';

export function DocReader() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: doc, isLoading, isError, error, refetch } = useDocument(id);
  useDocumentEvents(id);
  const removeDoc = useRemoveDocument();
  const setMeta = useSetDocumentMeta();
  const addToast = useUIStore((s) => s.addToast);
  const [view, setView] = useState<'original' | 'text'>('original');
  const [sectionNo, setSectionNo] = useState(1);

  const isPdf = doc?.ext === '.pdf';
  const parseable = doc?.status === 'ready';
  const stored = doc?.status === 'stored';

  useEffect(() => {
    if (doc && !isPdf) setView('text');
  }, [doc, isPdf]);

  if (isLoading) {
    return <div className="reader-state"><LoadingSpinner label="加载文档中…" /></div>;
  }
  if (isError || !doc) {
    return (
      <div className="reader-state">
        <EmptyState
          title="无法加载文档"
          description={error instanceof Error ? error.message : '文档不存在或服务不可用'}
          icon={EmptyStateIcons.library}
          action={<button type="button" className="btn btn-ghost" onClick={() => void refetch()}>重试</button>}
        />
      </div>
    );
  }

  return (
    <div className="doc-reader">
      <header className="doc-reader__head">
        <Link to="/sources" className="doc-reader__back" aria-label="返回资源库">←</Link>
        <div className="doc-reader__meta">
          <h1>{doc.title}</h1>
          <p className="muted small">
            {doc.filename} · {doc.total_sections > 0 ? `${doc.total_sections} 章` : doc.ext}
            {doc.status === 'parsing' && ' · 解析中…'}
          </p>
          <TagEditor
            tags={doc.tags ?? []}
            onChange={(tags) =>
              setMeta.mutate(
                { docId: doc.id, meta: { tags } },
                { onError: (e) => addToast({ type: 'error', message: e instanceof Error ? e.message : '标签保存失败' }) },
              )
            }
          />
        </div>
        <div className="doc-reader__actions">
          {parseable && (
            <div className="doc-reader__views" role="tablist">
              {isPdf && (
                <button type="button" role="tab" aria-selected={view === 'original'} className={`kind-tab ${view === 'original' ? 'is-active' : ''}`} onClick={() => setView('original')}>
                  原文
                </button>
              )}
              <button type="button" role="tab" aria-selected={view === 'text'} className={`kind-tab ${view === 'text' ? 'is-active' : ''}`} onClick={() => setView('text')}>
                文本
              </button>
            </div>
          )}
          <a className="btn glass-card glass-card--control liquid-glass--pill liquid-glass--interactive" href={getApi().docFileUrl(doc.id)} target="_blank" rel="noreferrer">
            打开原文件
          </a>
          <button
            type="button"
            className="icon-btn"
            aria-label="删除文档"
            onClick={() => {
              if (!window.confirm(`删除文档「${doc.title}」?此操作不可撤销。`)) return;
              removeDoc.mutate(doc.id, {
                onSuccess: () => {
                  addToast({ type: 'success', message: '文档已删除' });
                  navigate('/sources');
                },
                onError: (e) => addToast({ type: 'error', message: e instanceof Error ? e.message : '删除失败' }),
              });
            }}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width={16} height={16}>
              <path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2m3 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6" />
            </svg>
          </button>
        </div>
      </header>

      {doc.status === 'failed' && (
        <div className="doc-reader__failed" role="alert">
          解析失败:{doc.error || '未知原因'}
        </div>
      )}
      {stored && (
        <div className="doc-reader__stored">
          该格式暂不支持解析,已作为存档保存;可下载原文件查看。
        </div>
      )}
      {doc.status === 'parsing' && (
        <div className="reader-state"><LoadingSpinner label="解析中,完成后自动就绪…" /></div>
      )}

      {parseable && view === 'original' && isPdf && <PdfPane docId={doc.id} fileUrl={getApi().docFileUrl(doc.id)} />}
      {parseable && (view === 'text' || !isPdf) && (
        <div className="doc-reader__text">
          <aside className="doc-reader__outline">
            <h2 className="small muted">章节</h2>
            <ul>
              {doc.sections.map((s) => (
                <li key={s.section_no}>
                  <button
                    type="button"
                    className={`doc-reader__outline-item ${s.section_no === sectionNo ? 'is-active' : ''}`}
                    onClick={() => setSectionNo(s.section_no)}
                  >
                    {s.title || `第 ${s.section_no} 章`}
                  </button>
                </li>
              ))}
            </ul>
          </aside>
          <SectionPane
            docId={doc.id}
            sectionNo={sectionNo}
            onNav={(delta) => setSectionNo((n) => Math.min(doc.total_sections, Math.max(1, n + delta)))}
          />
        </div>
      )}
    </div>
  );
}

function SectionPane({ docId, sectionNo, onNav }: { docId: string; sectionNo: number; onNav: (delta: number) => void }) {
  const { data: section, isLoading } = useDocSection(docId, sectionNo);
  if (isLoading) return <div className="doc-reader__content"><LoadingSpinner /></div>;
  if (!section) return <div className="doc-reader__content muted">章不存在</div>;
  return (
    <div className="doc-reader__content">
      {section.title && <h2>{section.title}</h2>}
      <p className="muted small">
        第 {section.section_no} / {section.total_sections} 章
        {section.page_end > 0 && ` · 原文第 ${section.page_start}–${section.page_end} 页`}
      </p>
      <MarkdownRenderer content={section.text} />
      <div className="doc-reader__pager">
        <button type="button" className="btn glass-card glass-card--control liquid-glass--pill liquid-glass--interactive" disabled={sectionNo <= 1} onClick={() => onNav(-1)}>
          上一章
        </button>
        <button
          type="button"
          className="btn glass-card glass-card--control liquid-glass--pill liquid-glass--interactive"
          disabled={sectionNo >= section.total_sections}
          onClick={() => onNav(1)}
        >
          下一章
        </button>
      </div>
    </div>
  );
}

const PDFJS_SCALE_KEY = 'voyager-pdf-scale';

/** pdf.js 原版式分页视图(canvas 渲染;cmaps 由 public/pdfjs 提供,中文必需)。 */
function PdfPane({ docId, fileUrl }: { docId: string; fileUrl: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [pageNum, setPageNum] = useState(1);
  const [total, setTotal] = useState(0);
  const [failed, setFailed] = useState('');
  const [scale, setScale] = useState(() => {
    const raw = localStorage.getItem(PDFJS_SCALE_KEY);
    return raw ? Number(raw) : 1.2;
  });

  const docRef = useRef<import('pdfjs-dist').PDFDocumentProxy | null>(null);
  const taskRef = useRef<import('pdfjs-dist').PDFDocumentLoadingTask | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const pdfjs = await import('pdfjs-dist');
        pdfjs.GlobalWorkerOptions.workerSrc = new URL(
          'pdfjs-dist/build/pdf.worker.min.mjs',
          import.meta.url,
        ).toString();
        const task = pdfjs.getDocument({
          url: fileUrl,
          cMapUrl: '/pdfjs/cmaps/',
          cMapPacked: true,
          standardFontDataUrl: '/pdfjs/standard_fonts/',
        });
        taskRef.current = task;
        const pdf = await task.promise;
        if (cancelled) {
          void task.destroy();
          return;
        }
        docRef.current = pdf;
        setTotal(pdf.numPages);
      } catch (err) {
        if (!cancelled) setFailed(err instanceof Error ? err.message : 'PDF 加载失败');
      }
    })();
    return () => {
      cancelled = true;
      void taskRef.current?.destroy();
      taskRef.current = null;
      docRef.current = null;
    };
  }, [fileUrl]);

  useEffect(() => {
    let renderTask: import('pdfjs-dist').RenderTask | null = null;
    const render = async () => {
      const pdf = docRef.current;
      const canvas = canvasRef.current;
      if (!pdf || !canvas || pageNum < 1 || pageNum > total) return;
      const page = await pdf.getPage(pageNum);
      const viewport = page.getViewport({ scale: scale * window.devicePixelRatio });
      const ctx = canvas.getContext('2d');
      if (!ctx) return;
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      canvas.style.width = `${viewport.width / window.devicePixelRatio}px`;
      canvas.style.height = `${viewport.height / window.devicePixelRatio}px`;
      renderTask = page.render({ canvas, canvasContext: ctx, viewport });
      try {
        await renderTask.promise;
      } catch (err) {
        if (err instanceof Error && !err.message.includes('cancelled')) throw err;
      } finally {
        page.cleanup();
      }
    };
    void render();
    return () => {
      renderTask?.cancel();
    };
  }, [pageNum, total, scale, docId]);

  const changeScale = (delta: number) => {
    setScale((s) => {
      const next = Math.min(3, Math.max(0.5, s + delta));
      localStorage.setItem(PDFJS_SCALE_KEY, String(next));
      return next;
    });
  };

  if (failed) {
    return <div className="reader-state"><EmptyState title="PDF 加载失败" description={failed} icon={EmptyStateIcons.library} /></div>;
  }
  return (
    <div className="pdf-pane">
      <div className="pdf-pane__toolbar">
        <button type="button" className="page-btn" disabled={pageNum <= 1} onClick={() => setPageNum((n) => n - 1)} aria-label="上一页">‹</button>
        <span className="pdf-pane__page">{pageNum} / {total || '…'}</span>
        <button type="button" className="page-btn" disabled={pageNum >= total} onClick={() => setPageNum((n) => n + 1)} aria-label="下一页">›</button>
        <span className="pdf-pane__sep" />
        <button type="button" className="page-btn" onClick={() => changeScale(-0.2)} aria-label="缩小">−</button>
        <button type="button" className="page-btn" onClick={() => changeScale(0.2)} aria-label="放大">+</button>
      </div>
      <div className="pdf-pane__viewport">
        <canvas ref={canvasRef} />
        {total === 0 && <LoadingSpinner label="渲染 PDF…" />}
      </div>
    </div>
  );
}
