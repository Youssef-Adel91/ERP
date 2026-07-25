"use client";

import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Banknote } from "lucide-react";
import { toast } from "sonner";

const formSchema = z.object({
  contact_id: z.string().min(1, "Contact is required"),
  payment_type: z.enum(["inbound", "outbound"]),
  amount: z.coerce.number().min(0.01, "Amount must be greater than 0"),
  reference: z.string().min(1, "Reference is required"),
});

type FormValues = z.infer<typeof formSchema>;

export default function RecordPaymentPage() {
  const router = useRouter();
  const queryClient = useQueryClient();

  const { data: contacts } = useQuery({
    queryKey: ["contacts"],
    queryFn: () => apiClient.get("/contacts"),
  });

  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema) as any,
    defaultValues: {
      contact_id: "",
      payment_type: "inbound",
      amount: 0,
      reference: "",
    },
  });

  const createMutation = useMutation({
    mutationFn: (data: FormValues) => apiClient.post("/accounting/payments", data),
    onSuccess: () => {
      toast.success("Payment recorded successfully");
      queryClient.invalidateQueries({ queryKey: ["dashboard", "metrics"] });
      router.push("/dashboard");
    },
    onError: (error: any) => {
      toast.error(
        "Error recording payment", {
        description: error?.response?.data?.detail || "An unexpected error occurred",
      });
    },
  });

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-6 animate-in fade-in duration-300">
      <div className="flex items-center gap-3">
        <Banknote className="w-8 h-8 text-primary" />
        <div>
          <h1 className="text-3xl font-bold">Record Payment / Receipt</h1>
          <p className="text-slate-500">Record cash in or cash out.</p>
        </div>
      </div>

      <Form {...form}>
        <form onSubmit={form.handleSubmit((d) => createMutation.mutate(d))} className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Payment Details</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <FormField
                control={form.control}
                name="payment_type"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Type</FormLabel>
                    <Select onValueChange={field.onChange} defaultValue={field.value}>
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="Select type" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="inbound">Receipt (Cash In / From Customer)</SelectItem>
                        <SelectItem value="outbound">Payment (Cash Out / To Supplier)</SelectItem>
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="contact_id"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Contact (Customer/Supplier)</FormLabel>
                    <Select onValueChange={field.onChange} defaultValue={field.value}>
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="Select contact" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {Array.isArray(contacts) && contacts.map((c: any) => (
                          <SelectItem key={c.id} value={c.id}>
                            {c.name} ({c.contact_type})
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
                name="amount"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Amount</FormLabel>
                    <FormControl>
                      <Input type="number" step="0.01" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="reference"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Reference / Notes</FormLabel>
                    <FormControl>
                      <Input placeholder="e.g. Bank Transfer TX-123" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </CardContent>
          </Card>

          <div className="flex justify-end gap-4">
            <Button type="button" variant="outline" onClick={() => router.back()} disabled={createMutation.isPending}>
              Cancel
            </Button>
            <Button type="submit" disabled={createMutation.isPending}>
              {createMutation.isPending ? "Recording..." : "Record Payment"}
            </Button>
          </div>
        </form>
      </Form>
    </div>
  );
}
