/** 转发到 components/common/EmptyState,接受 message 别名(并转发 description/action)。 */
import { EmptyState as Raw } from '@/components/common/EmptyState';

export type WidgetEmptyStateProps = {
  title: string;
  description?: string;
  action?: React.ReactNode;
  message?: string;
};

export function EmptyState({ message, ...rest }: WidgetEmptyStateProps) {
  return <Raw {...rest} {...(message ? { description: message } : {})} />;
}
