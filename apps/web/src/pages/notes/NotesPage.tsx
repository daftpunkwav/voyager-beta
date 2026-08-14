/** 笔记页:三栏(列表/编辑/操作);?open=<id> 直开(chat 产物卡跳转入口)。 */

import { useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Degraded } from '@/shell/Degraded';
import { NoteList } from './NoteList';
import { NoteEditor } from './NoteEditor';
import { NoteMeta } from './NoteMeta';
import { useNotesStore } from './notesStore';

export function NotesPage() {
  const { loading, error, init, open } = useNotesStore();
  const [params, setParams] = useSearchParams();

  useEffect(() => {
    void init();
  }, [init]);

  // ?open=<id>:产物卡/外链直达打开(消费后清参数避免刷新重复定位)
  useEffect(() => {
    const target = params.get('open');
    if (target) {
      void open(target).catch(() => {
        // 打开失败(如已删除)静默,列表仍可用
      });
      params.delete('open');
      setParams(params, { replace: true });
    }
  }, [params, setParams, open]);

  if (error) {
    return (
      <Degraded
        code={error.code}
        message={`笔记服务不可用:${error.message}`}
        hint="其余页面不受影响"
        onRetry={() => void init()}
      />
    );
  }

  return (
    <section className="notes-page">
      {loading ? (
        <div className="loading-spinner">
          <div className="spinner" />
        </div>
      ) : (
        <>
          <NoteList />
          <NoteEditor />
          <NoteMeta />
        </>
      )}
    </section>
  );
}
