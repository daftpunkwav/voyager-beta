/** 导入中心:五合一导入对话框(GitHub URL / 库外搜索 / Stars / 文档上传 / 网址)。
 *
 * 文档上传 = uploadFile 落盘 + add_document 入库(两步组合流);
 * 网址 = save_url 抓取入库;仓库复用既有的 ImportUrlsModal 通道。
 */

import { useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { getApi } from '@/api/client';
import { useUIStore } from '@/stores/uiStore';

export type ImportTab = 'files' | 'web' | 'github';

const TABS: { key: ImportTab; label: string }[] = [
  { key: 'files', label: '文档' },
  { key: 'web', label: '网址' },
  { key: 'github', label: 'GitHub' },
];

const ACCEPT = '.pdf,.epub,.docx,.txt,.md,.markdown,.zip,.mobi,.azw3,.html';

interface ImportCenterProps {
  open: boolean;
  initialTab?: ImportTab;
  onClose: () => void;
}

export function ImportCenter({ open, initialTab = 'files', onClose }: ImportCenterProps) {
  const [tab, setTab] = useState<ImportTab>(initialTab);
  return (
    <div className="modal-overlay" onClick={onClose} hidden={!open}>
      {open && (
        <div className="modal import-center" role="dialog" aria-modal="true" aria-label="导入资料" onClick={(e) => e.stopPropagation()}>
          <header className="import-center__head">
            <h2>导入资料</h2>
            <nav className="import-center__tabs" role="tablist">
              {TABS.map((t) => (
                <button
                  key={t.key}
                  type="button"
                  role="tab"
                  aria-selected={tab === t.key}
                  className={`import-center__tab ${tab === t.key ? 'is-active' : ''}`}
                  onClick={() => setTab(t.key)}
                >
                  {t.label}
                </button>
              ))}
            </nav>
            <button type="button" className="icon-btn" aria-label="关闭" onClick={onClose}>
              ✕
            </button>
          </header>
          <div className="import-center__body">
            {tab === 'files' && <FilesPane onDone={onClose} />}
            {tab === 'web' && <WebPane onDone={onClose} />}
            {tab === 'github' && <GithubPane onDone={onClose} />}
          </div>
        </div>
      )}
    </div>
  );
}

/** 文档上传:点击/拖拽 → 上传 → 入库解析;未知格式收为存档。 */
function FilesPane({ onDone }: { onDone: () => void }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const addToast = useUIStore((s) => s.addToast);

  const upload = async (files: FileList | File[]) => {
    const list = Array.from(files);
    if (list.length === 0) return;
    setBusy(true);
    let ok = 0;
    let fail = 0;
    for (const f of list) {
      try {
        await getApi().uploadDocument(f);
        ok += 1;
      } catch (err) {
        fail += 1;
        addToast({
          type: 'error',
          message: `${f.name}:${err instanceof Error ? err.message : '上传失败'}`,
        });
      }
    }
    setBusy(false);
    if (ok > 0) {
      addToast({
        type: 'success',
        message: `已导入 ${ok} 个文档${fail > 0 ? `(失败 ${fail})` : ''},解析完成后可阅读`,
      });
      onDone();
    }
  };

  return (
    <div
      className={`import-drop ${dragging ? 'is-drag' : ''}`}
      onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        void upload(e.dataTransfer.files);
      }}
      onClick={() => inputRef.current?.click()}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') inputRef.current?.click(); }}
    >
      <input
        ref={inputRef}
        type="file"
        multiple
        accept={ACCEPT}
        hidden
        onChange={(e) => {
          if (e.target.files) void upload(e.target.files);
          e.target.value = '';
        }}
      />
      <div className="import-drop__icon" aria-hidden>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" width={40} height={40}>
          <path d="M12 16V4M6 10l6-6 6 6" />
          <path d="M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3" />
        </svg>
      </div>
      <p className="import-drop__title">{busy ? '上传中…' : '拖拽文件到这里,或点击选择'}</p>
      <p className="import-drop__hint">
        PDF / EPUB / DOCX / TXT / MD 自动分章解析;其他格式收为存档。单个 ≤200MB。
      </p>
    </div>
  );
}

/** 网址剪藏:粘贴 URL 列表逐条抓取。 */
function WebPane({ onDone }: { onDone: () => void }) {
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const addToast = useUIStore((s) => s.addToast);

  const save = async () => {
    const urls = text.split('\n').map((l) => l.trim()).filter(Boolean);
    if (urls.length === 0) return;
    setBusy(true);
    let ok = 0;
    let fail = 0;
    for (const url of urls) {
      try {
        await getApi().saveUrl(url);
        ok += 1;
      } catch (err) {
        fail += 1;
        addToast({
          type: 'error',
          message: err instanceof Error ? err.message : `${url} 抓取失败`,
        });
      }
    }
    setBusy(false);
    if (ok > 0) {
      addToast({ type: 'success', message: `已保存 ${ok} 个网页${fail > 0 ? `(失败 ${fail})` : ''}` });
      onDone();
    }
  };

  return (
    <div className="import-web">
      <textarea
        className="import-web__input"
        rows={5}
        placeholder={'粘贴网页链接(每行一个)\nhttps://example.com/article'}
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
      <p className="import-web__hint">抓取正文存入资料库;内网地址会被安全策略拒绝。</p>
      <div className="import-web__actions">
        <button type="button" className="btn btn-primary" disabled={busy || !text.trim()} onClick={() => void save()}>
          {busy ? '抓取中…' : '保存网页'}
        </button>
      </div>
    </div>
  );
}

/** GitHub:复用旧导入弹窗(URL 粘贴 / 搜索 / Stars 由既有组件承接)。 */
function GithubPane({ onDone }: { onDone: () => void }) {
  const qc = useQueryClient();
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const addToast = useUIStore((s) => s.addToast);

  const importRepos = async () => {
    const urls = text.split('\n').map((l) => l.trim()).filter(Boolean);
    if (urls.length === 0) return;
    setBusy(true);
    let ok = 0;
    let fail = 0;
    for (const url of urls) {
      try {
        await getApi().importRepo(url);
        ok += 1;
      } catch (err) {
        fail += 1;
        if (urls.length === 1) {
          addToast({
            type: 'error',
            message: err instanceof Error ? err.message : '导入失败',
          });
        }
      }
    }
    setBusy(false);
    void qc.invalidateQueries({ queryKey: ['projects'] });
    void qc.invalidateQueries({ queryKey: ['sourcesStream'] });
    if (ok > 0) {
      addToast({ type: 'success', message: `已导入 ${ok} 个仓库${fail > 0 ? `(失败 ${fail})` : ''}` });
      onDone();
    } else if (urls.length > 1) {
      addToast({ type: 'error', message: '导入失败,请检查链接' });
    }
  };

  return (
    <div className="import-web">
      <textarea
        className="import-web__input"
        rows={5}
        placeholder={'粘贴 GitHub 仓库链接(每行一个)\nhttps://github.com/langchain-ai/langgraph'}
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
      <p className="import-web__hint">后台克隆到本地;完成后可在图谱页建索引。</p>
      <div className="import-web__actions">
        <button type="button" className="btn btn-primary" disabled={busy || !text.trim()} onClick={() => void importRepos()}>
          {busy ? '导入中…' : '导入仓库'}
        </button>
      </div>
    </div>
  );
}
