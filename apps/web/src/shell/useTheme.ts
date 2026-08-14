/** 主题:读设置 appearance.theme → <html data-theme>(阶段 02 起支持热切换)。 */

import { useEffect } from 'react';
import { callCapability } from '@/bridge/client';

export function useTheme() {
  useEffect(() => {
    let alive = true;
    callCapability<{ key: string; value: string }>('settings', 'get_setting', {
      key: 'appearance.theme',
    })
      .then((item) => {
        if (alive && item?.value) {
          document.documentElement.dataset.theme = item.value;
        }
      })
      .catch(() => {
        // 读不到设置(如后端未起)保持默认主题,不打断壳渲染
      });
    return () => {
      alive = false;
    };
  }, []);
}
