'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import * as z from 'zod';
import { Users, Shield, Plus, ShieldCheck, Mail, Save, FileText, CheckCircle2 } from 'lucide-react';
import { toast } from 'sonner';

import { apiClient } from '@/lib/api-client';
import { useAppStore } from '@/store/use-app-store';
import { cn } from '@/lib/utils';
import { User } from '@/types/core';

import { Button, buttonVariants } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';

// ── Schema ───────────────────────────────────────────────────────────────────

const memberSchema = z.object({
  full_name: z.string().min(2, 'Name must be at least 2 characters'),
  email: z.string().email('Invalid email address'),
  password: z.string().min(8, 'Password must be at least 8 characters'),
  role: z.enum(['OWNER', 'SALES', 'WAREHOUSE', 'ACCOUNTING']),
});

type MemberFormValues = z.infer<typeof memberSchema>;

// ── Helpers ──────────────────────────────────────────────────────────────────

function getRoleBadgeColor(role: string) {
  switch (role) {
    case 'OWNER':
      return 'bg-purple-100 text-purple-800 border-purple-200';
    case 'SALES':
      return 'bg-blue-100 text-blue-800 border-blue-200';
    case 'WAREHOUSE':
      return 'bg-amber-100 text-amber-800 border-amber-200';
    case 'ACCOUNTING':
      return 'bg-emerald-100 text-emerald-800 border-emerald-200';
    default:
      return 'bg-slate-100 text-slate-800 border-slate-200';
  }
}

// ── Component ────────────────────────────────────────────────────────────────

export default function TeamPage() {
  const language = useAppStore((s) => s.language);
  const currentUser = useAppStore((s) => s.user);
  const isAr = language === 'ar';
  const queryClient = useQueryClient();
  const [isDialogOpen, setIsDialogOpen] = useState(false);

  // 1. Fetch Team
  const { data: team = [], isLoading } = useQuery<User[]>({
    queryKey: ['team'],
    queryFn: () => apiClient.get('/core/team'),
    enabled: !!currentUser, // Only fetch if we have a user
  });

  // 2. Create Mutation
  const form = useForm<MemberFormValues>({
    resolver: zodResolver(memberSchema),
    defaultValues: {
      full_name: '',
      email: '',
      password: '',
      role: 'SALES',
    },
  });

  const { mutate: createMember, isPending } = useMutation({
    mutationFn: (data: MemberFormValues) => apiClient.post('/core/team/', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['team'] });
      toast.success(isAr ? 'تمت إضافة العضو بنجاح' : 'Team member added successfully');
      setIsDialogOpen(false);
      form.reset();
    },
    onError: (err: Error) => {
      toast.error(err.message);
    },
  });

  const onSubmit = (data: MemberFormValues) => {
    createMember(data);
  };

  if (currentUser?.role !== 'OWNER') {
    return (
      <div className="p-8 flex flex-col items-center justify-center min-h-[50vh] text-center">
        <ShieldCheck className="w-16 h-16 text-red-500 mb-4" />
        <h2 className="text-2xl font-bold mb-2">
          {isAr ? 'غير مصرح' : 'Unauthorized'}
        </h2>
        <p className="text-muted-foreground">
          {isAr
            ? 'فقط مدير النظام (OWNER) يمكنه الوصول إلى هذه الصفحة.'
            : 'Only the OWNER can access this page.'}
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-5xl">
      {/* ── Header ── */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
            <Users className="w-6 h-6 text-primary" />
            {isAr ? 'إدارة الفريق والصلاحيات' : 'Team & Roles Management'}
          </h1>
          <p className="text-muted-foreground text-sm mt-1">
            {isAr
              ? 'إضافة وحذف المستخدمين وتعيين صلاحيات الوصول الخاصة بهم.'
              : 'Add, remove users and manage their access roles.'}
          </p>
        </div>

        <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
          <DialogTrigger className={cn(buttonVariants({ variant: 'default' }), "gap-2 shadow-sm font-bold h-11 px-6")}>
            <Plus className="w-4 h-4" />
            {isAr ? 'إضافة مستخدم جديد' : 'Add New User'}
          </DialogTrigger>
          <DialogContent className="sm:max-w-[425px]">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <Shield className="w-5 h-5 text-primary" />
                {isAr ? 'إضافة مستخدم جديد' : 'Add New User'}
              </DialogTitle>
            </DialogHeader>
            <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4 pt-4">
              <div className="space-y-2">
                <label className="text-sm font-bold flex items-center gap-2">
                  <FileText className="w-4 h-4 text-muted-foreground" />
                  {isAr ? 'الاسم بالكامل' : 'Full Name'}
                </label>
                <Input
                  {...form.register('full_name')}
                  placeholder={isAr ? 'أحمد محمد' : 'John Doe'}
                  disabled={isPending}
                />
                {form.formState.errors.full_name && (
                  <p className="text-xs text-destructive">{form.formState.errors.full_name.message}</p>
                )}
              </div>

              <div className="space-y-2">
                <label className="text-sm font-bold flex items-center gap-2">
                  <Mail className="w-4 h-4 text-muted-foreground" />
                  {isAr ? 'البريد الإلكتروني' : 'Email Address'}
                </label>
                <Input
                  type="email"
                  dir="ltr"
                  {...form.register('email')}
                  placeholder="name@company.com"
                  disabled={isPending}
                />
                {form.formState.errors.email && (
                  <p className="text-xs text-destructive">{form.formState.errors.email.message}</p>
                )}
              </div>

              <div className="space-y-2">
                <label className="text-sm font-bold flex items-center gap-2">
                  <ShieldCheck className="w-4 h-4 text-muted-foreground" />
                  {isAr ? 'كلمة المرور المؤقتة' : 'Temporary Password'}
                </label>
                <Input
                  type="text"
                  dir="ltr"
                  {...form.register('password')}
                  placeholder="Min 8 characters (e.g. Pass1234!)"
                  disabled={isPending}
                />
                {form.formState.errors.password && (
                  <p className="text-xs text-destructive">{form.formState.errors.password.message}</p>
                )}
              </div>

              <div className="space-y-2">
                <label className="text-sm font-bold">{isAr ? 'الصلاحية (الدور)' : 'Role'}</label>
                <Select
                  disabled={isPending}
                  onValueChange={(v) => form.setValue('role', v as any)}
                  defaultValue={form.getValues('role')}
                >
                  <SelectTrigger className="h-11">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="SALES">{isAr ? 'المبيعات (SALES)' : 'Sales (SALES)'}</SelectItem>
                    <SelectItem value="WAREHOUSE">{isAr ? 'المخازن (WAREHOUSE)' : 'Warehouse (WAREHOUSE)'}</SelectItem>
                    <SelectItem value="ACCOUNTING">{isAr ? 'الحسابات (ACCOUNTING)' : 'Accounting (ACCOUNTING)'}</SelectItem>
                    <SelectItem value="OWNER">{isAr ? 'مدير النظام (OWNER)' : 'Owner (OWNER)'}</SelectItem>
                  </SelectContent>
                </Select>
                {form.formState.errors.role && (
                  <p className="text-xs text-destructive">{form.formState.errors.role.message}</p>
                )}
              </div>

              <div className="pt-4 flex justify-end gap-2">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setIsDialogOpen(false)}
                  disabled={isPending}
                >
                  {isAr ? 'إلغاء' : 'Cancel'}
                </Button>
                <Button type="submit" disabled={isPending} className="gap-2 font-bold">
                  {isPending ? (
                    <span className="w-4 h-4 border-2 border-primary-foreground border-t-transparent rounded-full animate-spin" />
                  ) : (
                    <Save className="w-4 h-4" />
                  )}
                  {isAr ? 'حفظ المستخدم' : 'Save User'}
                </Button>
              </div>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      {/* ── Table ── */}
      <div className="bg-card rounded-xl shadow-sm border overflow-hidden">
        <Table>
          <TableHeader className="bg-muted/50">
            <TableRow>
              <TableHead className="font-bold">{isAr ? 'المستخدم' : 'User'}</TableHead>
              <TableHead className="font-bold">{isAr ? 'البريد الإلكتروني' : 'Email'}</TableHead>
              <TableHead className="font-bold">{isAr ? 'الصلاحية' : 'Role'}</TableHead>
              <TableHead className="font-bold">{isAr ? 'الحالة' : 'Status'}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={4} className="h-24 text-center">
                  <span className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin inline-block" />
                </TableCell>
              </TableRow>
            ) : team.length === 0 ? (
              <TableRow>
                <TableCell colSpan={4} className="h-24 text-center text-muted-foreground">
                  {isAr ? 'لا يوجد مستخدمين' : 'No users found'}
                </TableCell>
              </TableRow>
            ) : (
              team.map((member) => (
                <TableRow key={member.id} className="hover:bg-muted/30">
                  <TableCell className="font-medium">
                    {/* @ts-ignore -- backend returns full_name instead of name */}
                    {member.full_name || member.email.split('@')[0]}
                  </TableCell>
                  <TableCell className="font-mono text-sm text-muted-foreground" dir="ltr">
                    {member.email}
                  </TableCell>
                  <TableCell>
                    <span
                      className={cn(
                        'px-2.5 py-0.5 rounded-full text-xs font-bold border',
                        getRoleBadgeColor(member.role)
                      )}
                    >
                      {member.role}
                    </span>
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-1.5 text-sm">
                      <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                      <span>{isAr ? 'نشط' : 'Active'}</span>
                    </div>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
