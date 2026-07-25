'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { useAppStore } from '@/store/use-app-store';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { toast } from 'sonner';
import { 
  Puzzle, 
  Search, 
  Filter, 
  CheckCircle2, 
  Star,
  Download,
  Building,
  Briefcase,
  Users,
  ShoppingCart,
  Settings,
  ChevronRight,
  TrendingUp
} from 'lucide-react';
import type { PluginInfo } from '@/types/plugins';

const MOCK_PLUGINS = [
  {
    id: 'hr-pro',
    name: 'الموارد البشرية المتقدم',
    nameEn: 'Advanced HR',
    description: 'إدارة شاملة لشؤون الموظفين، الرواتب، تقييم الأداء، والحضور والانصراف مع دعم نظام البصمة.',
    descriptionEn: 'Comprehensive HR management including payroll, performance, and attendance with biometric support.',
    category: 'إداري',
    categoryEn: 'Administrative',
    provider: 'Trust Core',
    rating: 4.8,
    downloads: 1250,
    price: '99',
    icon: Users,
    status: 'installed',
    version: '2.1.0'
  },
  {
    id: 'inventory-plus',
    name: 'المخزون ونقاط البيع',
    nameEn: 'Inventory & POS',
    description: 'نظام متكامل لإدارة المخازن المتعددة، تتبع الباركود، ونقاط البيع السحابية للمتاجر.',
    descriptionEn: 'Integrated multi-warehouse management, barcode tracking, and cloud POS for retail.',
    category: 'مبيعات',
    categoryEn: 'Sales',
    provider: 'Trust Core',
    rating: 4.9,
    downloads: 3400,
    price: '149',
    icon: ShoppingCart,
    status: 'available',
    version: '1.5.2'
  },
  {
    id: 'crm-hub',
    name: 'إدارة علاقات العملاء',
    nameEn: 'CRM Hub',
    description: 'تتبع خطوط البيع، إدارة حملات التسويق، وخدمة العملاء مع ربط مباشر ببريد الشركة.',
    descriptionEn: 'Track sales pipelines, manage marketing campaigns, and customer service directly integrated with email.',
    category: 'تسويق',
    categoryEn: 'Marketing',
    provider: 'Trust Core',
    rating: 4.7,
    downloads: 2100,
    price: '79',
    icon: Briefcase,
    status: 'available',
    version: '3.0.1'
  },
  {
    id: 'manufacturing-erp',
    name: 'إدارة التصنيع والإنتاج',
    nameEn: 'Manufacturing ERP',
    description: 'تخطيط متطلبات المواد، أوامر الشغل، تكلفة الإنتاج، وجدولة المصانع.',
    descriptionEn: 'Material requirements planning, work orders, production costing, and factory scheduling.',
    category: 'تشغيلي',
    categoryEn: 'Operations',
    provider: 'Partner Labs',
    rating: 4.5,
    downloads: 850,
    price: '199',
    icon: Building,
    status: 'installed',
    version: '1.2.0'
  },
  {
    id: 'bi-analytics',
    name: 'لوحات القيادة الذكية',
    nameEn: 'BI Analytics',
    description: 'تحليلات أعمال متقدمة، تنبؤ مالي بالذكاء الاصطناعي، وتقارير ديناميكية.',
    descriptionEn: 'Advanced BI analytics, AI financial forecasting, and dynamic reports.',
    category: 'مالي',
    categoryEn: 'Financial',
    provider: 'Trust Core',
    rating: 5.0,
    downloads: 4200,
    price: '129',
    icon: TrendingUp,
    status: 'update',
    version: '4.0.0'
  }
];

export default function PluginsMarketplacePage() {
  const router = useRouter();
  const { language, activePlugins, setActivePlugins } = useAppStore();
  const isAr = language === 'ar';
  
  const [activeTab, setActiveTab] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');

  // We sync active status directly with our mock data for this UI demo
  const [plugins, setPlugins] = useState(MOCK_PLUGINS.map(p => ({
    ...p,
    // Initialize active status based on if it's already in the store (or mock it as active if it's installed/update)
    isActive: activePlugins.some(ap => ap.id === p.id) || p.status === 'update' || (p.status === 'installed' && p.id === 'hr-pro')
  })));

  const togglePlugin = (pluginId: string, currentStatus: boolean, pluginName: string) => {
    // Optimistic UI update
    setPlugins(plugins.map(p => p.id === pluginId ? { ...p, isActive: !currentStatus } : p));
    
    // Update store (we construct a dummy PluginInfo object)
    if (!currentStatus) {
      setActivePlugins([...activePlugins, { id: pluginId, nameAr: pluginName, nameEn: pluginName, isActive: true }]);
      toast.success(isAr ? `تم تفعيل ${pluginName} بنجاح` : `${pluginName} activated successfully`);
    } else {
      setActivePlugins(activePlugins.filter(p => p.id !== pluginId));
      toast.info(isAr ? `تم إيقاف ${pluginName}` : `${pluginName} deactivated`);
    }
  };

  const handleInstall = (pluginName: string) => {
    toast.success(isAr ? `جاري تثبيت ${pluginName}...` : `Installing ${pluginName}...`);
  };

  return (
    <div className="space-y-6 pb-24">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 bg-card p-6 border-b border-border -mx-6 -mt-6 mb-6">
        <div>
          <h1 className="text-3xl font-bold text-foreground flex items-center gap-3">
            <Puzzle className="w-8 h-8 text-primary" />
            {isAr ? 'سوق ملحقات Trust Core' : 'Trust Core Marketplace'}
          </h1>
          <p className="text-sm text-muted-foreground mt-2">
            {isAr ? 'اكتشف وقم بتثبيت التطبيقات الإضافية لتوسيع قدرات نظامك' : 'Discover and install add-ons to expand your system capabilities'}
          </p>
        </div>
        <div className="flex gap-3 w-full sm:w-auto">
          <Button 
            variant="outline" 
            className="gap-2 h-11 border-border shadow-sm font-bold text-foreground hover:bg-muted transition-colors"
            onClick={() => toast.info(isAr ? 'فتح التصفية المتقدمة...' : 'Opening advanced filters...')}
          >
            <Filter className="w-4 h-4" />
            {isAr ? 'تصفية' : 'Filter'}
          </Button>
          <Button 
            className="gap-2 h-11 px-6 font-bold shadow bg-accent text-accent-foreground hover:bg-accent-hover transition-colors"
            onClick={() => toast.info(isAr ? 'جاري عرض الملحقات المعتمدة...' : 'Showing approved plugins...')}
          >
            <CheckCircle2 className="w-5 h-5" />
            {isAr ? 'الملحقات المعتمدة' : 'Approved Plugins'}
          </Button>
        </div>
      </div>

      <div className="flex flex-col sm:flex-row gap-4 items-center justify-between mb-8">
        <div className="flex gap-2 w-full sm:w-auto overflow-x-auto pb-2 sm:pb-0 hide-scrollbar border-b border-border">
          {['الكل', 'مالي', 'مبيعات', 'إداري', 'تشغيلي'].map((tab, idx) => {
            const tabId = ['all', 'financial', 'sales', 'administrative', 'operations'][idx];
            const isActive = activeTab === tabId;
            return (
              <button
                key={tabId}
                onClick={() => setActiveTab(tabId)}
                className={`px-4 py-3 text-sm font-bold transition-all whitespace-nowrap border-b-2 
                  ${isActive ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground hover:border-border'}`}
              >
                {isAr ? tab : ['All', 'Financial', 'Sales', 'Admin', 'Operations'][idx]}
              </button>
            );
          })}
        </div>
        
        <div className="relative w-full sm:w-72">
          <div className="absolute inset-y-0 end-0 flex items-center pe-3 pointer-events-none">
            <Search className="w-4 h-4 text-muted-foreground" />
          </div>
          <Input 
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full h-10 bg-card border-border rounded-lg text-sm pe-10 ps-4 focus:ring-1 focus:ring-primary shadow-sm"
            placeholder={isAr ? 'ابحث عن تطبيق...' : 'Search for an app...'} 
          />
        </div>
      </div>

      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {plugins.map((plugin) => (
          <Card key={plugin.id} className="border-border shadow-sm hover:shadow-md transition-shadow flex flex-col relative overflow-hidden group">
            {plugin.status === 'update' && (
              <div className="absolute top-0 right-0 w-16 h-16 overflow-hidden z-10">
                <div className={`absolute top-4 -right-4 bg-warning text-warning-foreground font-bold text-[10px] py-1 px-8 transform rotate-45 text-center ${!isAr && '-rotate-45 left-auto -left-4'}`}>
                  UPDATE
                </div>
              </div>
            )}
            
            <CardHeader className="p-5 pb-0 flex flex-row items-start justify-between">
              <div className="w-14 h-14 rounded-xl bg-muted/50 border border-border flex items-center justify-center flex-shrink-0">
                <plugin.icon className="w-7 h-7 text-primary" />
              </div>
              <Badge variant="secondary" className="bg-muted text-muted-foreground hover:bg-muted font-normal text-xs rounded-full px-3 shadow-none">
                {isAr ? plugin.category : plugin.categoryEn}
              </Badge>
            </CardHeader>
            <CardContent className="p-5 pt-4 flex-1 flex flex-col">
              <h3 className="font-bold text-foreground text-lg line-clamp-1 mb-1">
                {isAr ? plugin.name : plugin.nameEn}
              </h3>
              <p className="text-xs text-muted-foreground mb-3 flex items-center gap-1 font-mono" dir="ltr">
                <span className="font-sans">By {plugin.provider}</span> • v{plugin.version}
              </p>
              <p className="text-sm text-muted-foreground line-clamp-2 mb-4 flex-1">
                {isAr ? plugin.description : plugin.descriptionEn}
              </p>
              
              <div className="flex items-center justify-between mt-auto pt-4 border-t border-border/50">
                <div className="flex items-center gap-3">
                  <div className="flex items-center gap-1 text-xs font-bold text-foreground">
                    <Star className="w-4 h-4 fill-warning text-warning" />
                    <span className="font-mono pt-0.5" dir="ltr">{plugin.rating}</span>
                  </div>
                  <div className="flex items-center gap-1 text-xs text-muted-foreground">
                    <Download className="w-3.5 h-3.5" />
                    <span className="font-mono pt-0.5" dir="ltr">{plugin.downloads}</span>
                  </div>
                </div>
                
                {plugin.status === 'available' ? (
                  <Button 
                    className="h-8 px-4 text-xs font-bold bg-primary text-primary-foreground hover:bg-primary/90 shadow-sm"
                    onClick={() => handleInstall(isAr ? plugin.name : plugin.nameEn)}
                  >
                    {isAr ? 'تثبيت' : 'Install'}
                  </Button>
                ) : (
                  <Button 
                    variant={plugin.isActive ? 'outline' : 'default'}
                    className={`h-8 px-4 text-xs font-bold shadow-sm ${plugin.isActive ? 'border-border text-foreground hover:bg-muted' : 'bg-success hover:bg-success/90 text-white'}`}
                    onClick={() => togglePlugin(plugin.id, plugin.isActive, isAr ? plugin.name : plugin.nameEn)}
                  >
                    {plugin.isActive ? (isAr ? 'إيقاف' : 'Deactivate') : (isAr ? 'تفعيل' : 'Activate')}
                  </Button>
                )}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="fixed bottom-0 start-0 lg:start-64 end-0 bg-sidebar border-t border-border shadow-[0_-10px_30px_-15px_rgba(0,0,0,0.3)] z-40 transition-all duration-300">
        <div className="max-w-7xl mx-auto px-6 h-20 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="w-10 h-10 rounded-full bg-accent/20 flex items-center justify-center">
              <Settings className="w-5 h-5 text-accent" />
            </div>
            <div>
              <p className="font-bold text-white text-sm">{isAr ? 'ترقية إلى النسخة المؤسسية' : 'Upgrade to Enterprise'}</p>
              <p className="text-xs text-sidebar-subtitle">{isAr ? 'احصل على وصول غير محدود لجميع الملحقات' : 'Get unlimited access to all plugins'}</p>
            </div>
          </div>
          
          <Button 
            className="relative z-10 h-12 px-8 bg-accent hover:bg-accent-hover text-accent-foreground font-bold shadow-lg flex-shrink-0 text-base"
            onClick={() => router.push('/upgrade')}
          >
            {isAr ? 'ترقية الحساب الآن' : 'Upgrade Account Now'}
            <ChevronRight className="w-5 h-5 ms-2 rtl:rotate-180" />
          </Button>
        </div>
      </div>
    </div>
  );
}
