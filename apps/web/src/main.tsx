import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { initApiClient } from '@/api/client';
import { App } from '@/App';
import '@/styles/design-system.css';
import '@/styles/liquid-glass.css';
import '@/styles/shell.css';
import '@/styles/pages/index.css';
import '@/styles/global.css';
import 'highlight.js/styles/github-dark.min.css';

async function bootstrap() {
  await initApiClient();

  const rootEl = document.getElementById('root');
  if (!rootEl) {
    throw new Error('Root element #root not found');
  }

  createRoot(rootEl).render(
    <StrictMode>
      <App />
    </StrictMode>
  );
}

void bootstrap();
