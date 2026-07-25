"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm, useFieldArray } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { apiClient } from "@/lib/api-client";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ArrowLeft, Loader2, Plus, Trash2 } from "lucide-react";
import Link from "next/link";

interface Item {
  id: string;
  name: string;
  sku: string;
}

const adjustmentLineSchema = z.object({
  item_id: z.string().min(1, "Please select an item."),
  quantity_change: z.coerce.number().refine((val) => val !== 0, {
    message: "Quantity cannot be zero.",
  }),
});

const adjustmentSchema = z.object({
  reason: z.enum(["initial_balance", "damage", "correction"], {
    message: "Please select a reason.",
  }),
  date: z.string().min(1, "Date is required"),
  notes: z.string().optional(),
  lines: z.array(adjustmentLineSchema).min(1, "At least one item is required."),
});

type AdjustmentFormValues = z.infer<typeof adjustmentSchema>;

export default function NewAdjustmentPage() {
  const router = useRouter();
  const queryClient = useQueryClient();

  const { data: items, isLoading: itemsLoading } = useQuery<Item[]>({
    queryKey: ["inventory", "items"],
    queryFn: () => apiClient.get("/inventory/items"),
  });

  const form = useForm<AdjustmentFormValues>({
    resolver: zodResolver(adjustmentSchema) as any,
    defaultValues: {
      reason: "initial_balance",
      date: new Date().toISOString().split("T")[0],
      notes: "",
      lines: [{ item_id: "", quantity_change: 0 }],
    },
  });

  const { fields, append, remove } = useFieldArray({
    name: "lines",
    control: form.control,
  });

  const { mutate, isPending } = useMutation({
    mutationFn: (data: AdjustmentFormValues) => {
      // API expects ISO datetime string
      const payload = {
        ...data,
        date: new Date(data.date).toISOString(),
      };
      return apiClient.post("/inventory/adjustments", payload);
    },
    onSuccess: () => {
      toast.success("Stock adjustment created successfully.");
      queryClient.invalidateQueries({ queryKey: ["inventory", "adjustments"] });
      // Also invalidate items because stock quantities changed!
      queryClient.invalidateQueries({ queryKey: ["inventory", "items"] });
      router.push("/inventory/adjustments");
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : "Failed to create adjustment.");
    },
  });

  function onSubmit(data: AdjustmentFormValues) {
    mutate(data);
  }

  return (
    <div className="p-6 space-y-6 max-w-5xl mx-auto animate-in fade-in zoom-in-95 duration-300">
      <div className="flex items-center gap-4">
        <Link href="/inventory/adjustments">
          <Button variant="outline" size="icon">
            <ArrowLeft className="h-4 w-4" />
          </Button>
        </Link>
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-slate-900 dark:text-white">
            New Stock Adjustment (تسوية مخزون جديدة)
          </h1>
          <p className="text-slate-500 dark:text-slate-400 mt-1">
            Adjust stock levels for damages, corrections, or initial balances.
          </p>
        </div>
      </div>

      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Master Details</CardTitle>
              <CardDescription>General information about this adjustment.</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <FormField
                  control={form.control}
                  name="reason"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Reason (سبب التسوية)</FormLabel>
                      <Select onValueChange={field.onChange} defaultValue={field.value}>
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue placeholder="Select a reason" />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          <SelectItem value="initial_balance">Initial Balance (رصيد افتتاحي)</SelectItem>
                          <SelectItem value="correction">Correction (تسوية وتعديل)</SelectItem>
                          <SelectItem value="damage">Damage / Loss (تالف أو مفقود)</SelectItem>
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="date"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Date (التاريخ)</FormLabel>
                      <FormControl>
                        <Input type="date" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="notes"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Notes (ملاحظات)</FormLabel>
                      <FormControl>
                        <Input placeholder="Optional notes..." {...field} value={field.value || ""} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <div>
                <CardTitle>Adjustment Items</CardTitle>
                <CardDescription>Select items and enter the quantity to adjust. Use positive values to add stock, and negative to deduct.</CardDescription>
              </div>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => append({ item_id: "", quantity_change: 0 })}
              >
                <Plus className="h-4 w-4 mr-2" />
                Add Row
              </Button>
            </CardHeader>
            <CardContent className="space-y-4">
              {fields.length === 0 && (
                <div className="text-center p-4 border rounded text-slate-500">
                  No items added. Click "Add Row" to start.
                </div>
              )}
              {form.formState.errors.lines?.root && (
                <p className="text-sm font-medium text-destructive">
                  {form.formState.errors.lines.root.message}
                </p>
              )}
              
              {fields.map((field, index) => (
                <div key={field.id} className="flex flex-col sm:flex-row gap-4 items-start sm:items-end p-4 border rounded-lg bg-slate-50/50 dark:bg-slate-800/20">
                  <FormField
                    control={form.control}
                    name={`lines.${index}.item_id`}
                    render={({ field: selectField }) => (
                      <FormItem className="flex-1 w-full sm:w-auto">
                        <FormLabel>Item (الصنف)</FormLabel>
                        <Select onValueChange={selectField.onChange} defaultValue={selectField.value}>
                          <FormControl>
                            <SelectTrigger>
                              <SelectValue placeholder={itemsLoading ? "Loading..." : "Select an item"} />
                            </SelectTrigger>
                          </FormControl>
                          <SelectContent>
                            {items?.map(item => (
                              <SelectItem key={item.id} value={item.id}>
                                {item.sku} - {item.name}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={form.control}
                    name={`lines.${index}.quantity_change`}
                    render={({ field: inputField }) => (
                      <FormItem className="w-full sm:w-32">
                        <FormLabel>Qty Change (+/-)</FormLabel>
                        <FormControl>
                          <Input type="number" step="any" {...inputField} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <Button
                    type="button"
                    variant="destructive"
                    size="icon"
                    className="mb-0 sm:mb-0.5"
                    disabled={fields.length === 1}
                    onClick={() => remove(index)}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              ))}
            </CardContent>
          </Card>

          <div className="flex justify-end gap-4">
            <Link href="/inventory/adjustments">
              <Button type="button" variant="ghost">Cancel</Button>
            </Link>
            <Button type="submit" disabled={isPending} className="bg-primary text-primary-foreground min-w-[150px]">
              {isPending ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Processing...
                </>
              ) : (
                "Confirm Adjustment"
              )}
            </Button>
          </div>
        </form>
      </Form>
    </div>
  );
}
