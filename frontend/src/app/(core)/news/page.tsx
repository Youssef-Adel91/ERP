'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import * as z from 'zod/v4';
import { Plus, Newspaper, Loader2, Megaphone } from 'lucide-react';
import { toast } from 'sonner';
import { format, formatDistanceToNow } from 'date-fns';
import { ar } from 'date-fns/locale';

import { apiClient } from '@/lib/api-client';
import { useAppStore } from '@/store/use-app-store';

// ── Types ─────────────────────────────────────────────────────────────────────

interface Announcement {
  id: string;
  title: string;
  content: string;
  created_by: string | null;
  created_at: string;
}

const announcementSchema = z.object({
  title: z.string().min(2, 'العنوان مطلوب').max(255),
  content: z.string().min(5, 'المحتوى يجب أن يكون 5 أحرف على الأقل'),
});

type AnnouncementForm = z.infer<typeof announcementSchema>;

// ── Component ─────────────────────────────────────────────────────────────────

export default function NewsPage() {
  const { user } = useAppStore();
  const queryClient = useQueryClient();
  const [isDialogOpen, setIsDialogOpen] = useState(false);

  // Fetch announcements
  const { data: announcements, isLoading } = useQuery<Announcement[]>({
    queryKey: ['news'],
    queryFn: () => apiClient.get('/core/news/'),
  });

  // Create announcement mutation
  const { mutate: createAnnouncement, isPending: isCreating } = useMutation({
    mutationFn: (data: AnnouncementForm) => apiClient.post('/core/news/', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['news'] });
      toast.success('تم نشر الإعلان بنجاح');
      setIsDialogOpen(false);
      reset();
    },
    onError: (err: Error) => {
      toast.error(err.message || 'فشل في نشر الإعلان');
    },
  });

  // Form setup
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<AnnouncementForm>({
    resolver: zodResolver(announcementSchema),
  });

  const onSubmit = (data: AnnouncementForm) => {
    createAnnouncement(data);
  };

  return (
    <div className="w-full max-w-5xl mx-auto p-4 md:p-6 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 bg-white p-6 rounded-2xl border border-[#E4E2E3] shadow-sm">
        <div>
          <h1 className="text-2xl font-bold text-[#040D1B] flex items-center gap-2">
            <Megaphone className="w-6 h-6 text-[#FF9800]" />
            الأخبار والإعلانات
          </h1>
          <p className="text-[#75777D] mt-1 text-sm">
            آخر التحديثات والإعلانات الخاصة بالشركة
          </p>
        </div>
        
        {user?.role === 'OWNER' && (
          <button
            onClick={() => setIsDialogOpen(true)}
            className="flex items-center gap-2 bg-[#FF9800] hover:bg-[#E6890A] text-white px-4 py-2.5 rounded-xl font-bold text-sm transition-all"
          >
            <Plus className="w-4 h-4" />
            إضافة إعلان جديد
          </button>
        )}
      </div>

      {/* Main Feed */}
      <div className="space-y-4">
        {isLoading ? (
          <div className="flex flex-col items-center justify-center py-20 text-[#75777D]">
            <Loader2 className="w-8 h-8 animate-spin mb-4 text-[#FF9800]" />
            <p>جاري تحميل الأخبار...</p>
          </div>
        ) : announcements?.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 bg-white rounded-2xl border border-[#E4E2E3] border-dashed text-[#75777D]">
            <Newspaper className="w-12 h-12 mb-4 text-[#BEC7DB]" />
            <p className="font-semibold text-[#040D1B]">لا توجد إعلانات</p>
            <p className="text-sm mt-1">لم يتم نشر أي أخبار حتى الآن.</p>
          </div>
        ) : (
          announcements?.map((announcement) => (
            <div key={announcement.id} className="bg-white p-6 rounded-2xl border border-[#E4E2E3] shadow-sm hover:border-[#FF9800]/30 transition-colors">
              <div className="flex justify-between items-start mb-3">
                <h2 className="text-lg font-bold text-[#040D1B]">
                  {announcement.title}
                </h2>
                <div className="text-[12px] text-[#75777D] flex flex-col items-end">
                  <span>
                    {formatDistanceToNow(new Date(announcement.created_at), { addSuffix: true, locale: ar })}
                  </span>
                  <span className="text-[#BEC7DB]" title={format(new Date(announcement.created_at), 'PPP pp', { locale: ar })}>
                    {format(new Date(announcement.created_at), 'MMM d, yyyy')}
                  </span>
                </div>
              </div>
              <p className="text-[#4A4B51] text-[15px] leading-relaxed whitespace-pre-wrap">
                {announcement.content}
              </p>
            </div>
          ))
        )}
      </div>

      {/* Create Dialog (Simple conditional render for simplicity) */}
      {isDialogOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#040D1B]/40 backdrop-blur-sm p-4">
          <div className="bg-white w-full max-w-lg rounded-2xl shadow-xl overflow-hidden animate-in fade-in zoom-in-95 duration-200">
            <div className="p-6 border-b border-[#E4E2E3]">
              <h2 className="text-xl font-bold text-[#040D1B]">نشر إعلان جديد</h2>
            </div>
            
            <form onSubmit={handleSubmit(onSubmit)} className="p-6 space-y-4">
              <div>
                <label className="block text-sm font-semibold text-[#040D1B] mb-1.5">عنوان الإعلان</label>
                <input
                  type="text"
                  placeholder="مثال: تحديث مواعيد العمل"
                  {...register('title')}
                  className={`w-full h-11 rounded-lg border bg-white px-4 text-sm outline-none transition-all focus:border-[#FF9800] focus:ring-1 focus:ring-[#FF9800] ${errors.title ? 'border-red-500' : 'border-[#C5C6CC]'}`}
                />
                {errors.title && <p className="text-xs text-red-500 mt-1">{errors.title.message}</p>}
              </div>

              <div>
                <label className="block text-sm font-semibold text-[#040D1B] mb-1.5">نص الإعلان</label>
                <textarea
                  placeholder="اكتب محتوى الإعلان هنا..."
                  rows={5}
                  {...register('content')}
                  className={`w-full rounded-lg border bg-white p-4 text-sm outline-none transition-all focus:border-[#FF9800] focus:ring-1 focus:ring-[#FF9800] resize-none ${errors.content ? 'border-red-500' : 'border-[#C5C6CC]'}`}
                />
                {errors.content && <p className="text-xs text-red-500 mt-1">{errors.content.message}</p>}
              </div>

              <div className="flex items-center justify-end gap-3 pt-4">
                <button
                  type="button"
                  onClick={() => setIsDialogOpen(false)}
                  className="px-5 py-2.5 rounded-xl font-semibold text-[#4A4B51] hover:bg-[#F4F4F5] transition-colors"
                >
                  إلغاء
                </button>
                <button
                  type="submit"
                  disabled={isCreating}
                  className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-[#040D1B] hover:bg-[#1A2235] text-white font-semibold transition-all disabled:opacity-70"
                >
                  {isCreating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Megaphone className="w-4 h-4" />}
                  نشر الإعلان
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
