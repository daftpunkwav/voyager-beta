/** 导入对话框:多行 GitHub URL + 分类,逐条导入;CONFLICT 显示"已导入"。 */

import { useState } from 'react';
import { type ImportOutcome, useSourcesStore } from './sourcesStore';

const URL_RE = /^https:\/\/github\.com\/[\w.-]+\/[\w.-]+\/?$/;

export function ImportDialog({ onDone }: { onDone: () => void }) {
  const importUrls = useSourcesStore((s) => s.importUrls);
  const [text, setText] = useState('');
  const [category, setCategory] = useState('');
  const [outcomes, setOutcomes] = useState<ImportOutcome[] | null>(null);
  const [busy, setBusy] = useState(false);

  const urls = text
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean);
  const invalid = urls.filter((u) => !URL_RE.test(u));

  const run = async () => {
    setBusy(true);
    try {
      setOutcomes(await importUrls(urls, category.trim()));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="import-dialog">
      <div className="label">导入 GitHub 仓库</div>
      <textarea
        className="setting-input"
        rows={4}
        value={text}
        placeholder={'https://github.com/owner/name\n(每行一个)'}
        onChange={(e) => setText(e.target.value)}
      />
      <input
        className="setting-input"
        value={category}
        placeholder="分类(可空,如:Agent 框架)"
        onChange={(e) => setCategory(e.target.value)}
      />
      {invalid.length > 0 ? (
        <div className="setting-field__error small">非法链接:{invalid.join('、')}</div>
      ) : null}
      {outcomes ? (
        <div className="import-dialog__outcomes small">
          {outcomes.map((o) => (
            <div key={o.url} className={o.ok ? '' : 'setting-field__error'}>
              {o.url}:{o.message}
            </div>
          ))}
        </div>
      ) : null}
      <div className="ask-actions">
        <button
          type="button"
          className="btn btn-primary"
          disabled={busy || urls.length === 0 || invalid.length > 0}
          onClick={() => void run()}
        >
          {busy ? '导入中…' : `导入 ${urls.length || ''} 个`}
        </button>
        <button type="button" className="btn" onClick={onDone}>
          关闭
        </button>
      </div>
    </div>
  );
}
