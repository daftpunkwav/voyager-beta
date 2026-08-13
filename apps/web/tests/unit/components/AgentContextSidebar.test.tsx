import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { ReactNode } from 'react';
import { AgentContextSidebar } from '@/components/agent/AgentContextSidebar';

vi.mock('@/api/client', () => ({
  getApi: () => ({
    getUserProfile: vi.fn().mockResolvedValue({
      data: { memory_items: [], goals: [], tech_proficiency: {} },
    }),
    updateUserProfile: vi.fn(),
    getAgentSession: vi.fn().mockResolvedValue({
      data: { id: 's1', project_ids: [], project_id: null, messages: [] },
    }),
    listProjects: vi.fn().mockResolvedValue({ data: { items: [] } }),
  }),
}));

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe('AgentContextSidebar', () => {
  const baseProps = {
    sessionId: null as string | null,
    toolLogOpen: false,
    onToggleToolLog: vi.fn(),
    toolCalls: new Map<string, { name: string; result?: unknown }>(),
  };

  it('渲染上下文面板主区块', () => {
    render(<AgentContextSidebar {...baseProps} />, { wrapper });
    expect(screen.getByText(/当前上下文/)).toBeInTheDocument();
  });
});
