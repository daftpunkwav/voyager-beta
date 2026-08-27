/** 转发到 components/common/EmptyState,接受 message 别名(并转发 description/action/icon)。 */
import { EmptyState as Raw, EmptyStateIcons } from '@/components/common/EmptyState';

export type WidgetEmptyStateProps = {
  title: string;
  description?: string;
  action?: React.ReactNode;
  message?: string;
  icon?: React.ReactNode;
};

export function EmptyState({ message, ...rest }: WidgetEmptyStateProps) {
  return <Raw {...rest} {...(message ? { description: message } : {})} />;
}

export { EmptyStateIcons };
