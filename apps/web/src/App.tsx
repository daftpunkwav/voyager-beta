import { lazy, Suspense, useEffect } from 'react';
import {
  createBrowserRouter,
  Navigate,
  RouterProvider,
} from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AppShell, AgentShell, NotesShell } from '@/components/layout/AppShell';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { ErrorBoundary } from '@/components/common/ErrorBoundary';
import { useAuthStore } from '@/stores/authStore';

const OverviewPage = lazy(() =>
  import('@/pages/OverviewPage').then((m) => ({ default: m.OverviewPage }))
);
const ProjectsPage = lazy(() =>
  import('@/pages/ProjectsPage').then((m) => ({ default: m.ProjectsPage }))
);
const ProjectDetailPage = lazy(() =>
  import('@/pages/ProjectDetailPage').then((m) => ({ default: m.ProjectDetailPage }))
);
const AgentPage = lazy(() =>
  import('@/pages/AgentPage').then((m) => ({ default: m.AgentPage }))
);
const GraphPage = lazy(() =>
  import('@/pages/GraphPage').then((m) => ({ default: m.GraphPage }))
);
const CodeGraphPage = lazy(() =>
  import('@/pages/CodeGraphPage').then((m) => ({ default: m.CodeGraphPage }))
);
const UsagePage = lazy(() =>
  import('@/pages/UsagePage').then((m) => ({ default: m.UsagePage }))
);
const NotesPage = lazy(() =>
  import('@/pages/NotesPage').then((m) => ({ default: m.NotesPage }))
);
const SettingsPage = lazy(() =>
  import('@/pages/SettingsPage').then((m) => ({ default: m.SettingsPage }))
);
const ProfilePage = lazy(() =>
  import('@/pages/ProfilePage').then((m) => ({ default: m.ProfilePage }))
);

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000,
      gcTime: 30 * 60 * 1000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

function Lazy({ children }: { children: React.ReactNode }) {
  return <Suspense fallback={<LoadingSpinner fullScreen />}>{children}</Suspense>;
}

const router = createBrowserRouter([
  {
    path: '/',
    element: <AppShell />,
    children: [
      {
        index: true,
        element: (
          <Lazy>
            <OverviewPage />
          </Lazy>
        ),
      },
      {
        path: 'projects',
        element: (
          <Lazy>
            <ProjectsPage />
          </Lazy>
        ),
      },
      {
        path: 'projects/:id',
        element: (
          <Lazy>
            <ProjectDetailPage />
          </Lazy>
        ),
      },
      {
        path: 'graph',
        element: (
          <Lazy>
            <GraphPage />
          </Lazy>
        ),
      },
      {
        path: 'graph/projects/:id',
        element: (
          <Lazy>
            <CodeGraphPage />
          </Lazy>
        ),
      },
      {
        path: 'usage',
        element: (
          <Lazy>
            <UsagePage />
          </Lazy>
        ),
      },
      {
        path: 'settings',
        element: (
          <Lazy>
            <SettingsPage />
          </Lazy>
        ),
      },
      {
        path: 'profile',
        element: (
          <Lazy>
            <ProfilePage />
          </Lazy>
        ),
      },
    ],
  },
  {
    path: '/agent',
    element: <AgentShell />,
    children: [
      {
        index: true,
        element: (
          <Lazy>
            <AgentPage />
          </Lazy>
        ),
      },
      {
        path: 'sessions/:sessionId',
        element: (
          <Lazy>
            <AgentPage />
          </Lazy>
        ),
      },
    ],
  },
  {
    path: '/notes',
    element: <NotesShell />,
    children: [
      {
        index: true,
        element: (
          <Lazy>
            <NotesPage />
          </Lazy>
        ),
      },
    ],
  },
  { path: '*', element: <Navigate to="/" replace /> },
]);

function LocalUserBootstrap({ children }: { children: React.ReactNode }) {
  const fetchMe = useAuthStore((s) => s.fetchMe);
  useEffect(() => {
    void fetchMe();
  }, [fetchMe]);
  return <>{children}</>;
}

export function App() {
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <LocalUserBootstrap>
          <RouterProvider router={router} />
        </LocalUserBootstrap>
      </QueryClientProvider>
    </ErrorBoundary>
  );
}
