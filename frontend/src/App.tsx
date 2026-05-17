import { HashRouter, Routes, Route } from 'react-router-dom';
import type { ReactNode } from 'react';
import { Loader2, LogIn } from 'lucide-react';
import { AuthProvider, useAuth } from '@/context/AuthContext';
import { AppProvider } from '@/context/AppContext';
import { TopNav } from '@/components/TopNav';
import { Button } from '@/components/ui/button';
import { Dashboard } from '@/pages/Dashboard';
import { Landing } from '@/pages/Landing';
import { CreateSession } from '@/pages/CreateSession';
import { SessionDetail } from '@/pages/SessionDetail';
import { Revise } from '@/pages/Revise';
import { Listening } from '@/pages/Listening';
import { PodcastPreview } from '@/pages/PodcastPreview';
import { NotFound } from '@/pages/NotFound';
import { I18nProvider, useI18n } from '@/i18n';

function AuthGate({ children }: { children: ReactNode }) {
  const { user, loading, error, login } = useAuth();
  const { t } = useI18n();

  if (loading) {
    return (
      <div className="min-h-[55vh] flex items-center justify-center text-slate-500">
        <Loader2 className="w-5 h-5 animate-spin" />
      </div>
    );
  }

  if (!user) {
    return (
      <div className="min-h-[55vh] flex items-center justify-center">
        <div className="w-full max-w-[380px] rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
          <div className="w-10 h-10 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center mb-4">
            <LogIn className="w-5 h-5" />
          </div>
          <h1 className="text-[20px] font-bold text-slate-900 tracking-tight">{t('auth.signInTitle')}</h1>
          <p className="text-[13px] text-slate-500 mt-1.5">
            {t('auth.signInDescription')}
          </p>
          {error && (
            <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-[12px] text-red-700">
              {error}
            </div>
          )}
          <Button
            type="button"
            onClick={login}
            className="mt-5 w-full bg-indigo-500 hover:bg-indigo-600 text-white h-9 text-[13px] font-semibold gap-1.5"
          >
            <LogIn className="w-4 h-4" />
            {t('common.login')}
          </Button>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}

function App() {
  return (
    <I18nProvider>
      <AuthProvider>
        <AppProvider>
          <HashRouter>
            <div className="min-h-screen bg-slate-50 flex flex-col">
              <TopNav />
              <main className="flex-1 px-4 sm:px-6 lg:px-8 py-6 sm:py-8">
                <div className="max-w-[1100px] mx-auto">
                  <Routes>
                    <Route path="/" element={<Landing />} />
                    <Route path="/dashboard" element={<AuthGate><Dashboard /></AuthGate>} />
                    <Route path="/create" element={<AuthGate><CreateSession /></AuthGate>} />
                    <Route path="/session/:id" element={<AuthGate><SessionDetail /></AuthGate>} />
                    <Route path="/session/:id/podcast-preview" element={<AuthGate><PodcastPreview /></AuthGate>} />
                    <Route path="/session/:id/revise" element={<AuthGate><Revise /></AuthGate>} />
                    <Route path="/session/:id/listening" element={<AuthGate><Listening /></AuthGate>} />
                    <Route path="*" element={<NotFound />} />
                  </Routes>
                </div>
              </main>
            </div>
          </HashRouter>
        </AppProvider>
      </AuthProvider>
    </I18nProvider>
  );
}

export default App;
