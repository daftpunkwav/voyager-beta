/** 图片灯箱:点击放大;ESC/遮罩关闭;遵循全局动效约定(reduced-motion 自动降级)。 */

import { useEffect } from 'react';

interface LightboxProps {
  src: string | null;
  alt?: string;
  onClose: () => void;
}

export function Lightbox({ src, alt, onClose }: LightboxProps) {
  useEffect(() => {
    if (!src) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [src, onClose]);

  if (!src) return null;
  return (
    <div className="lightbox" role="dialog" aria-modal="true" aria-label={alt ?? '图片预览'} onClick={onClose}>
      <img src={src} alt={alt ?? ''} className="lightbox__img" />
      <button type="button" className="lightbox__close" aria-label="关闭" onClick={onClose}>
        ✕
      </button>
    </div>
  );
}
