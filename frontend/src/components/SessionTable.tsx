import { useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { Search, RefreshCw, FileAudio, FileText, Trash2 } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { StatusBadge } from './StatusBadge';
import { useSessionFilter } from '@/hooks/useSessionFilter';
import { formatDuration, formatDate } from '@/utils/formatTime';
import type { Session } from '@/types';
import { useApp } from '@/context/AppContext';
import { useI18n } from '@/i18n';
import { deleteSession as deleteSessionApi } from '@/lib/api/sessions';

interface SessionTableProps {
  sessions: Session[];
}

export function SessionTable({ sessions }: SessionTableProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const { dispatch, refreshSessions } = useApp();
  const { t } = useI18n();

  const filteredSessions = useSessionFilter(sessions, searchQuery);

  const handleRefresh = useCallback(async () => {
    setIsRefreshing(true);
    await refreshSessions();
    setIsRefreshing(false);
  }, [refreshSessions]);

  const handleDelete = useCallback(
    async (event: React.MouseEvent, sessionId: string) => {
      event.preventDefault();
      event.stopPropagation();
      if (!window.confirm(t('sessionTable.deleteConfirm'))) return;
      setDeletingId(sessionId);
      try {
        await deleteSessionApi(sessionId);
        dispatch({ type: 'DELETE_SESSION', payload: sessionId });
      } catch (err) {
        console.error('Failed to delete session', err);
        window.alert(t('sessionTable.deleteFailed'));
      } finally {
        setDeletingId(null);
      }
    },
    [dispatch, t],
  );

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex items-center justify-between gap-4">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <Input
            placeholder={t('sessionTable.searchPlaceholder')}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-10 bg-white border-slate-200 focus:border-indigo-300 focus:ring-indigo-200 text-[13px] h-10"
          />
        </div>
        <button
          onClick={handleRefresh}
          className="p-2.5 rounded-lg border border-slate-200 bg-white text-slate-500 hover:text-slate-700 hover:border-slate-300 transition-all"
        >
          <RefreshCw className={`w-4 h-4 ${isRefreshing ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* Mobile list */}
      <div className="space-y-2 sm:hidden">
        {filteredSessions.map((session) => (
          <div key={session.id} className="relative">
            <button
              type="button"
              onClick={(e) => handleDelete(e, session.id)}
              disabled={deletingId === session.id}
              title={t('sessionTable.delete')}
              className="absolute right-2 top-2 z-10 p-1.5 rounded-md text-slate-300 hover:text-red-600 hover:bg-red-50 transition-all duration-150 disabled:opacity-50"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          <Link
            to={`/session/${session.id}`}
            className="block rounded-lg border border-slate-200 bg-white p-3 shadow-sm transition-colors hover:bg-slate-50"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="flex min-w-0 items-center gap-3">
                <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${
                  session.type === 'audio' ? 'bg-violet-50 text-violet-500' : 'bg-sky-50 text-sky-500'
                }`}>
                  {session.type === 'audio' ? <FileAudio className="w-4 h-4" /> : <FileText className="w-4 h-4" />}
                </div>
                <div className="min-w-0">
                  <p className="truncate text-[13px] font-medium text-slate-800">{session.title}</p>
                  {session.description && (
                    <p className="truncate text-[11px] text-slate-400">{session.description}</p>
                  )}
                </div>
              </div>
              <div className="shrink-0">
                <StatusBadge status={session.status} />
              </div>
            </div>
            <div className="mt-3 flex items-center gap-2 text-[11px] text-slate-500">
              <span className={`rounded-md px-2 py-0.5 font-medium ${
                session.type === 'audio'
                  ? 'bg-violet-50 text-violet-600'
                  : 'bg-sky-50 text-sky-600'
              }`}>
                {session.type === 'audio' ? t('common.audio') : t('common.script')}
              </span>
              <span className="tabular-nums">{formatDuration(session.duration)}</span>
              <span className="h-1 w-1 rounded-full bg-slate-300" />
              <span>{formatDate(session.createdAt)}</span>
            </div>
          </Link>
          </div>
        ))}
      </div>
      {filteredSessions.length === 0 && (
        <div className="rounded-lg border border-slate-200 bg-white py-12 text-center shadow-sm sm:hidden">
          <p className="text-[14px] text-slate-400">{t('sessionTable.noSessions')}</p>
        </div>
      )}

      {/* Table */}
      <div className="hidden bg-white rounded-xl border border-slate-200 overflow-hidden shadow-sm sm:block">
        <table className="w-full">
          <thead>
            <tr className="border-b border-slate-100 bg-slate-50/50">
              <th className="text-left text-[10px] font-semibold text-slate-500 uppercase tracking-wider py-3 px-5">{t('common.session')}</th>
              <th className="text-left text-[10px] font-semibold text-slate-500 uppercase tracking-wider py-3 px-4 w-[100px]">{t('common.type')}</th>
              <th className="text-left text-[10px] font-semibold text-slate-500 uppercase tracking-wider py-3 px-4 w-[100px]">{t('common.duration')}</th>
              <th className="text-left text-[10px] font-semibold text-slate-500 uppercase tracking-wider py-3 px-4 w-[132px]">{t('common.status')}</th>
              <th className="text-left text-[10px] font-semibold text-slate-500 uppercase tracking-wider py-3 px-4 w-[100px]">{t('common.created')}</th>
              <th className="py-3 px-4 w-[60px]"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {filteredSessions.map((session) => (
              <tr
                key={session.id}
                className="group hover:bg-slate-50/80 transition-colors duration-150 cursor-pointer"
              >
                <td className="py-3.5 px-5">
                  <Link to={`/session/${session.id}`} className="flex items-center gap-3">
                    <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${
                      session.type === 'audio' ? 'bg-violet-50 text-violet-500' : 'bg-sky-50 text-sky-500'
                    }`}>
                      {session.type === 'audio' ? <FileAudio className="w-4 h-4" /> : <FileText className="w-4 h-4" />}
                    </div>
                    <div className="min-w-0">
                      <p className="text-[13px] font-medium text-slate-800 truncate group-hover:text-indigo-600 transition-colors">{session.title}</p>
                      {session.description && (
                        <p className="text-[11px] text-slate-400 truncate">{session.description}</p>
                      )}
                    </div>
                  </Link>
                </td>
                <td className="py-3.5 px-4">
                  <Link to={`/session/${session.id}`}>
                    <span className={`text-[11px] font-medium px-2 py-0.5 rounded-md ${
                      session.type === 'audio'
                        ? 'bg-violet-50 text-violet-600'
                        : 'bg-sky-50 text-sky-600'
                    }`}>
                      {session.type === 'audio' ? t('common.audio') : t('common.script')}
                    </span>
                  </Link>
                </td>
                <td className="py-3.5 px-4 text-[13px] text-slate-500 tabular-nums">
                  <Link to={`/session/${session.id}`}>{formatDuration(session.duration)}</Link>
                </td>
                <td className="py-3.5 px-4">
                  <Link to={`/session/${session.id}`} className="block max-w-full overflow-hidden">
                    <StatusBadge status={session.status} />
                  </Link>
                </td>
                <td className="py-3.5 px-4 text-[12px] text-slate-500">
                  <Link to={`/session/${session.id}`}>{formatDate(session.createdAt)}</Link>
                </td>
                <td className="py-3.5 px-4">
                  <div className="flex items-center gap-1">
                    <button
                      type="button"
                      onClick={(e) => handleDelete(e, session.id)}
                      disabled={deletingId === session.id}
                      title={t('sessionTable.delete')}
                      className="p-1.5 rounded-md text-slate-300 hover:text-red-600 hover:bg-red-50 transition-all duration-150 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                    <Link
                      to={`/session/${session.id}`}
                      className="p-1.5 rounded-md text-slate-300 hover:text-indigo-600 hover:bg-indigo-50 transition-all duration-150 block"
                    >
                      <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9 18l6-6-6-6"/></svg>
                    </Link>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {filteredSessions.length === 0 && (
          <div className="py-16 text-center">
            <p className="text-[14px] text-slate-400">{t('sessionTable.noSessions')}</p>
          </div>
        )}
      </div>
    </div>
  );
}
