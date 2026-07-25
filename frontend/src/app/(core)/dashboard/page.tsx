"use client";

import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Banknote, TrendingUp, Users, ArrowDownRight, ArrowUpRight, Plus, Receipt } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import Link from "next/link";
import { Button } from "@/components/ui/button";

interface DashboardMetrics {
  total_revenue: number;
  total_receivables: number;
  total_payables: number;
  cash_balance: number;
}

export default function DashboardPage() {
  const { data: metrics, isLoading } = useQuery<DashboardMetrics>({
    queryKey: ["dashboard", "metrics"],
    queryFn: () => apiClient.get("/dashboard/metrics"),
  });

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-8 animate-in fade-in duration-300">
      <div>
        <h1 className="text-4xl font-bold tracking-tight text-slate-900 dark:text-white">Main Dashboard</h1>
        <p className="text-slate-500 mt-2 text-lg">Financial overview and quick actions.</p>
      </div>

      {/* Metrics Section */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <Card className="bg-emerald-50 dark:bg-emerald-950/20 border-emerald-200">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-emerald-800 dark:text-emerald-400">Total Revenue</CardTitle>
            <TrendingUp className="w-4 h-4 text-emerald-600" />
          </CardHeader>
          <CardContent>
            {isLoading ? <Skeleton className="h-8 w-24" /> : (
              <div className="text-3xl font-bold text-emerald-900 dark:text-emerald-100">
                {Number(metrics?.total_revenue || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </div>
            )}
            <p className="text-xs text-emerald-600 mt-1">Confirmed Sales</p>
          </CardContent>
        </Card>

        <Card className="bg-blue-50 dark:bg-blue-950/20 border-blue-200">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-blue-800 dark:text-blue-400">Cash Balance</CardTitle>
            <Banknote className="w-4 h-4 text-blue-600" />
          </CardHeader>
          <CardContent>
            {isLoading ? <Skeleton className="h-8 w-24" /> : (
              <div className="text-3xl font-bold text-blue-900 dark:text-blue-100">
                {Number(metrics?.cash_balance || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </div>
            )}
            <p className="text-xs text-blue-600 mt-1">Available Funds</p>
          </CardContent>
        </Card>

        <Card className="bg-orange-50 dark:bg-orange-950/20 border-orange-200">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-orange-800 dark:text-orange-400">Accounts Receivable</CardTitle>
            <ArrowDownRight className="w-4 h-4 text-orange-600" />
          </CardHeader>
          <CardContent>
            {isLoading ? <Skeleton className="h-8 w-24" /> : (
              <div className="text-3xl font-bold text-orange-900 dark:text-orange-100">
                {Number(metrics?.total_receivables || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </div>
            )}
            <p className="text-xs text-orange-600 mt-1">Owed by Customers</p>
          </CardContent>
        </Card>

        <Card className="bg-rose-50 dark:bg-rose-950/20 border-rose-200">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-rose-800 dark:text-rose-400">Accounts Payable</CardTitle>
            <ArrowUpRight className="w-4 h-4 text-rose-600" />
          </CardHeader>
          <CardContent>
            {isLoading ? <Skeleton className="h-8 w-24" /> : (
              <div className="text-3xl font-bold text-rose-900 dark:text-rose-100">
                {Number(metrics?.total_payables || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </div>
            )}
            <p className="text-xs text-rose-600 mt-1">Owed to Suppliers</p>
          </CardContent>
        </Card>
      </div>

      {/* Quick Actions */}
      <h2 className="text-2xl font-semibold mt-10">Quick Actions</h2>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mt-4">
        <Link href="/sales/invoices/new">
          <Button variant="outline" className="w-full h-24 text-lg justify-start gap-4 px-6 hover:bg-slate-50 dark:hover:bg-slate-900 border-2">
            <div className="bg-emerald-100 p-3 rounded-full text-emerald-600">
              <TrendingUp className="w-6 h-6" />
            </div>
            New Sales Invoice
          </Button>
        </Link>
        <Link href="/purchases/invoices/new">
          <Button variant="outline" className="w-full h-24 text-lg justify-start gap-4 px-6 hover:bg-slate-50 dark:hover:bg-slate-900 border-2">
            <div className="bg-rose-100 p-3 rounded-full text-rose-600">
              <Receipt className="w-6 h-6" />
            </div>
            New Purchase Invoice
          </Button>
        </Link>
        <Link href="/accounting/payments/new">
          <Button variant="outline" className="w-full h-24 text-lg justify-start gap-4 px-6 hover:bg-slate-50 dark:hover:bg-slate-900 border-2">
            <div className="bg-blue-100 p-3 rounded-full text-blue-600">
              <Banknote className="w-6 h-6" />
            </div>
            Record Payment / Receipt
          </Button>
        </Link>
      </div>
    </div>
  );
}
