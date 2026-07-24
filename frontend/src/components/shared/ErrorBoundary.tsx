'use client';

import React, { Component, ErrorInfo, ReactNode } from 'react';
import { useAppStore } from '@/store/use-app-store';
import { Card, CardContent } from '@/components/ui/card';
import { AlertOctagon } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface Props {
  children?: ReactNode;
}

interface State {
  hasError: boolean;
  error?: Error;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('Uncaught error:', error, errorInfo);
  }

  public render() {
    if (this.state.hasError) {
      return <ErrorView error={this.state.error} onReset={() => this.setState({ hasError: false })} />;
    }

    return this.props.children;
  }
}

function ErrorView({ error, onReset }: { error?: Error, onReset: () => void }) {
  const language = useAppStore((state) => state.language);
  const isAr = language === 'ar';

  return (
    <div className="flex items-center justify-center p-6 h-full w-full">
      <Card className="w-full max-w-md border-danger bg-danger-bg">
        <CardContent className="pt-6 flex flex-col items-center text-center space-y-4">
          <div className="p-3 bg-danger/10 rounded-full text-danger">
            <AlertOctagon className="w-10 h-10" />
          </div>
          <div>
            <h2 className="text-xl font-bold text-danger">
              {isAr ? 'عذراً، حدث خطأ غير متوقع' : 'Oops, an unexpected error occurred'}
            </h2>
            <p className="text-sm text-danger/80 mt-2">
              {error?.message || (isAr ? 'فشل تحميل هذا المكون. يرجى المحاولة لاحقاً.' : 'Failed to load this component. Please try again later.')}
            </p>
          </div>
          <Button variant="outline" className="border-danger text-danger hover:bg-danger hover:text-white" onClick={onReset}>
            {isAr ? 'إعادة المحاولة' : 'Try Again'}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
