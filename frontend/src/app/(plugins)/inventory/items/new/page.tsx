"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { apiClient } from "@/lib/api-client";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ArrowLeft, Loader2 } from "lucide-react";
import Link from "next/link";

const itemSchema = z.object({
  name: z.string().min(2, "Name must be at least 2 characters."),
  name_ar: z.string().optional(),
  sku: z.string().min(2, "SKU must be at least 2 characters.").regex(/^[a-zA-Z0-9-_]+$/, "SKU must be alphanumeric (dashes and underscores allowed)."),
  description: z.string().optional(),
  category: z.string().optional(),
  price: z.coerce.number().min(0, "Price cannot be negative."),
  cost: z.coerce.number().min(0, "Cost cannot be negative."),
});

type ItemFormValues = z.infer<typeof itemSchema>;

export default function NewItemPage() {
  const router = useRouter();
  const queryClient = useQueryClient();

  const form = useForm<ItemFormValues>({
    resolver: zodResolver(itemSchema) as any,
    defaultValues: {
      name: "",
      name_ar: "",
      sku: "",
      description: "",
      category: "",
      price: 0,
      cost: 0,
    },
  });

  const { mutate, isPending } = useMutation({
    mutationFn: (data: ItemFormValues) => apiClient.post("/inventory/items", data),
    onSuccess: () => {
      toast.success("Item created successfully (تم إضافة الصنف بنجاح).");
      queryClient.invalidateQueries({ queryKey: ["inventory", "items"] });
      router.push("/inventory/items");
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : "Failed to create item.");
    },
  });

  function onSubmit(data: ItemFormValues) {
    mutate(data);
  }

  return (
    <div className="p-6 space-y-6 max-w-4xl mx-auto animate-in fade-in zoom-in-95 duration-300">
      <div className="flex items-center gap-4">
        <Link href="/inventory/items">
          <Button variant="outline" size="icon">
            <ArrowLeft className="h-4 w-4" />
          </Button>
        </Link>
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-slate-900 dark:text-white">
            Add New Item (إضافة صنف جديد)
          </h1>
          <p className="text-slate-500 dark:text-slate-400 mt-1">
            Create a new SKU in your inventory catalog.
          </p>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Item Details</CardTitle>
          <CardDescription>Enter the primary information for this item.</CardDescription>
        </CardHeader>
        <CardContent>
          <Form {...form}>
            <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <FormField
                  control={form.control}
                  name="sku"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>SKU (رقم الصنف)</FormLabel>
                      <FormControl>
                        <Input placeholder="e.g. GL-ACC-001" {...field} />
                      </FormControl>
                      <FormDescription>Unique identifier for this item.</FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="category"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Category (التصنيف)</FormLabel>
                      <FormControl>
                        <Input placeholder="e.g. Glass Accessories" {...field} value={field.value || ""} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <FormField
                  control={form.control}
                  name="name"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Name in English</FormLabel>
                      <FormControl>
                        <Input placeholder="e.g. Securite Glass Hinge" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="name_ar"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Name in Arabic (الاسم بالعربي)</FormLabel>
                      <FormControl>
                        <Input placeholder="مفصلة زجاج سيكوريت" dir="rtl" {...field} value={field.value || ""} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>

              <FormField
                control={form.control}
                name="description"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Description (الوصف)</FormLabel>
                    <FormControl>
                      <Input placeholder="Optional details..." {...field} value={field.value || ""} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <FormField
                  control={form.control}
                  name="price"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Selling Price (سعر البيع)</FormLabel>
                      <FormControl>
                        <Input type="number" step="0.01" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="cost"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Cost Price (سعر التكلفة)</FormLabel>
                      <FormControl>
                        <Input type="number" step="0.01" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>

              <div className="flex justify-end gap-4 pt-4 border-t">
                <Link href="/inventory/items">
                  <Button type="button" variant="ghost">Cancel</Button>
                </Link>
                <Button type="submit" disabled={isPending} className="bg-primary text-primary-foreground min-w-[120px]">
                  {isPending ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Saving...
                    </>
                  ) : (
                    "Save Item"
                  )}
                </Button>
              </div>

            </form>
          </Form>
        </CardContent>
      </Card>
    </div>
  );
}
