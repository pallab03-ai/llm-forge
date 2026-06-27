"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowLeft, FileUp } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Suspense, use, useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { DatasetUploadZone } from "@/components/datasets/dataset-upload-zone";
import { UploadProgress } from "@/components/datasets/upload-progress";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PageHeader } from "@/components/ui/page-header";
import { Spinner } from "@/components/ui/spinner";
import {
  DATASET_LABELS,
  FORMAT_LABELS,
  datasetFormatValues,
  datasetTypeValues,
  uploadDatasetSchema,
  type UploadDatasetInput,
} from "@/features/datasets/schemas";
import { useUploadDataset } from "@/features/datasets/queries";
import { ApiError } from "@/services/api-client";

type UploadPageProps = {
  searchParams: Promise<{ datasetId?: string }>;
};

function UploadForm({ datasetId }: { datasetId: string | undefined }) {
  const router = useRouter();
  const isNewVersion = Boolean(datasetId);
  const backHref = datasetId ? `/datasets/${datasetId}` : "/datasets";

  const [file, setFile] = useState<File | null>(null);
  const [progress, setProgress] = useState({ loaded: 0, total: 0 });
  const [controller, setController] = useState<AbortController | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    setValue,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<UploadDatasetInput>({
    resolver: zodResolver(uploadDatasetSchema),
    defaultValues: {
      name: "",
      description: "",
      datasetType: "instruction_tuning",
      format: "jsonl",
    },
  });

  const format = watch("format");
  const upload = useUploadDataset();

  function detectFormatFromName(name: string): UploadDatasetInput["format"] | null {
    const lower = name.toLowerCase();
    if (lower.endsWith(".csv")) return "csv";
    if (lower.endsWith(".jsonl")) return "jsonl";
    if (lower.endsWith(".json")) return "json";
    return null;
  }

  function onFilePicked(picked: File | null) {
    setFile(picked);
    if (picked) {
      const detected = detectFormatFromName(picked.name);
      if (detected) setValue("format", detected, { shouldDirty: true });
    }
  }

  const onSubmit = handleSubmit(async (values) => {
    setSubmitError(null);
    if (!file) {
      setSubmitError("Choose a file to upload.");
      return;
    }
    const formData = new FormData();
    formData.append("file", file);
    formData.append("name", values.name);
    formData.append("dataset_type", values.datasetType);
    formData.append("format", values.format);
    if (values.description) formData.append("description", values.description);

    const ac = new AbortController();
    setController(ac);
    setProgress({ loaded: 0, total: file.size });
    try {
      const dataset = await upload.mutateAsync({ formData, signal: ac.signal });
      toast.success(isNewVersion ? "New version uploaded." : "Dataset uploaded.");
      router.push(`/datasets/${dataset.id}`);
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        setSubmitError("Upload cancelled.");
        return;
      }
      if (error instanceof ApiError) {
        setSubmitError(error.message);
        return;
      }
      setSubmitError("Network error. Check your connection and try again.");
    } finally {
      setController(null);
    }
  });

  const isUploading = isSubmitting || upload.isPending;
  const uploadStatus: "uploading" | "success" | "error" = submitError
    ? "error"
    : isUploading
      ? "uploading"
      : "success";

  return (
    <div className="space-y-8">
      <Link href={backHref} className={buttonVariants({ variant: "ghost", size: "sm" })}>
        <ArrowLeft className="h-4 w-4" />
        Back
      </Link>
      <PageHeader
        title={isNewVersion ? "Upload new version" : "Upload dataset"}
        description={
          isNewVersion
            ? "Add a new version to an existing dataset. The version number increments automatically."
            : "Bring a CSV, JSON, or JSONL file into your workspace."
        }
      />

      <form className="grid grid-cols-1 gap-6 lg:grid-cols-3" onSubmit={onSubmit} noValidate>
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-base">File</CardTitle>
            <CardDescription>Drag and drop or pick a file. Format is auto-detected from the extension.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <DatasetUploadZone file={file} onFile={onFilePicked} disabled={isUploading} />

            {file ? (
              <UploadProgress
                fileName={file.name}
                loaded={progress.loaded}
                total={progress.total || file.size}
                status={uploadStatus}
                errorMessage={submitError ?? undefined}
                onCancel={
                  isUploading && controller
                    ? () => {
                        controller.abort();
                        setController(null);
                      }
                    : undefined
                }
              />
            ) : null}

            {submitError && !file ? (
              <p role="alert" className="text-sm text-destructive">
                {submitError}
              </p>
            ) : null}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Details</CardTitle>
            <CardDescription>Metadata that the backend stores with the dataset.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="name">Name</Label>
              <Input
                id="name"
                placeholder="my-finetune-corpus"
                invalid={Boolean(errors.name)}
                {...register("name")}
                disabled={isUploading}
              />
              {errors.name ? <p className="text-xs text-destructive">{errors.name.message}</p> : null}
            </div>

            <div className="space-y-2">
              <Label htmlFor="description">Description</Label>
              <textarea
                id="description"
                rows={3}
                placeholder="Optional. What is this dataset for?"
                className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                {...register("description")}
                disabled={isUploading}
              />
              {errors.description ? (
                <p className="text-xs text-destructive">{errors.description.message}</p>
              ) : null}
            </div>

            <div className="space-y-2">
              <Label htmlFor="datasetType">Type</Label>
              <select
                id="datasetType"
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                {...register("datasetType")}
                disabled={isUploading}
              >
                {datasetTypeValues.map((v) => (
                  <option key={v} value={v}>
                    {DATASET_LABELS[v]}
                  </option>
                ))}
              </select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="format">Format</Label>
              <select
                id="format"
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                {...register("format")}
                disabled={isUploading}
              >
                {datasetFormatValues.map((v) => (
                  <option key={v} value={v}>
                    {FORMAT_LABELS[v]}
                  </option>
                ))}
              </select>
              {file ? (
                <p className="text-xs text-muted-foreground">
                  Detected from filename: <span className="font-medium">{FORMAT_LABELS[format]}</span>
                </p>
              ) : null}
            </div>

            <Button type="submit" className="w-full" disabled={isUploading || !file}>
              {isUploading ? (
                <Spinner size="sm" label="Uploading" />
              ) : (
                <>
                  <FileUp className="h-4 w-4" />
                  {isNewVersion ? "Upload version" : "Upload dataset"}
                </>
              )}
            </Button>
          </CardContent>
        </Card>
      </form>
    </div>
  );
}

export default function UploadDatasetPage({ searchParams }: UploadPageProps) {
  // ponytail: use(searchParams) suspends until the Promise settles. The
  // Suspense boundary is the page itself; tests can either wait for the
  // form to appear (findBy) or render inside their own Suspense.
  const params = use(searchParams);
  return (
    <Suspense fallback={<div className="p-8 text-sm text-muted-foreground">Loading…</div>}>
      <UploadForm datasetId={params?.datasetId} />
    </Suspense>
  );
}
