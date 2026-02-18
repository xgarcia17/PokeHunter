"use client";

import { useRef, useState, type ChangeEvent } from "react";

type UploadResponse =
  | {
      ok: true;
      name: string;
      type: string;
      size: number;
    }
  | {
      ok?: false;
      error: string;
    };

const ALLOWED_TYPES = ["image/jpeg", "image/png"] as const;
const MAX_MB = 8;
const MAX_BYTES = MAX_MB * 1024 * 1024;

function validateFile(file: File): string | null {
  if (!ALLOWED_TYPES.includes(file.type as (typeof ALLOWED_TYPES)[number])) {
    return "Please upload a JPEG or PNG image.";
  }
  if (file.size > MAX_BYTES) {
    return `File is too large. Max size is ${MAX_MB}MB.`;
  }
  return null;
}

async function uploadToNextRoute(file: File): Promise<UploadResponse> {
  const fd = new FormData();
  fd.append("file", file);

  const res = await fetch("/api/upload", {
    method: "POST",
    body: fd,
  });

  let data: any = null;
  try {
    data = await res.json();
  } catch {
    // ignore
  }

  if (!res.ok) {
    const msg = data?.error ?? `Upload failed (${res.status})`;
    throw new Error(msg);
  }

  return data as UploadResponse;
}

export default function Scanner() {
  const inputRef = useRef<HTMLInputElement | null>(null);

  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [status, setStatus] = useState<"idle" | "uploading" | "done" | "error">(
    "idle",
  );
  const [error, setError] = useState<string | null>(null);
  const [serverResult, setServerResult] = useState<UploadResponse | null>(null);

  function pickFile() {
    inputRef.current?.click();
  }

  function setPreview(file: File) {
    const url = URL.createObjectURL(file);
    setPreviewUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return url;
    });
  }

  async function handleFile(file: File) {
    setStatus("idle");
    setError(null);
    setServerResult(null);

    const validationError = validateFile(file);
    if (validationError) {
      setStatus("error");
      setError(validationError);
      return;
    }

    setPreview(file);
    setStatus("uploading");

    try {
      const result = await uploadToNextRoute(file);
      setServerResult(result);
      setStatus("done");
    } catch (e) {
      setStatus("error");
      setError(e instanceof Error ? e.message : "Upload failed");
    }
  }

  function onFileInputChange(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
    // allow reselecting same file
    e.currentTarget.value = "";
  }

  function reset() {
    setStatus("idle");
    setError(null);
    setServerResult(null);
    setPreviewUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return null;
    });
  }

  return (
    <div className="bg-white rounded-2xl shadow-lg w-full max-w-4xl mx-auto p-6 md:p-8 overflow-hidden">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl md:text-3xl font-bold text-gray-900 mb-2">
          PokéCard Scanner
        </h1>
        <p className="text-sm md:text-base text-gray-600">
          Upload a photo of your Pokémon card for instant identification and
          pricing
        </p>
      </div>

      {/* Hidden file input */}
      <input
        ref={inputRef}
        type="file"
        accept={ALLOWED_TYPES.join(",")}
        className="hidden"
        onChange={onFileInputChange}
      />

      {/* Upload box */}
      <div className="border-2 border-dashed hover:border-purple-200 rounded-xl px-4 py-8 md:px-8 md:py-10 text-center flex flex-col items-center gap-4">
        {previewUrl ? (
          <>
            <img
              src={previewUrl}
              alt="Uploaded preview"
              className="max-h-64 w-auto rounded-lg border"
            />
            <button
              type="button"
              onClick={reset}
              className="text-xs md:text-sm text-purple-700 hover:text-purple-900 underline cursor-pointer"
            >
              Remove &amp; choose another
            </button>
          </>
        ) : (
          <>
            <div className="text-4xl md:text-5xl mb-1">📷</div>
            <p className="text-xs md:text-sm text-gray-500">
              No image selected yet
            </p>
          </>
        )}

        <div className="mt-2">
          <h2 className="text-base md:text-lg font-semibold text-gray-900">
            Upload Image of Your Pokémon Card
          </h2>
          <p className="text-xs md:text-sm text-gray-600 mt-1">
            supports JPEG or PNG up to {MAX_MB}MB
          </p>
        </div>

        {/* 👉 Only show the main button when there is NO preview */}
        {!previewUrl && (
          <button
            type="button"
            onClick={pickFile}
            disabled={status === "uploading"}
            className="mt-3 bg-gray-900 text-white px-5 py-2 text-sm rounded-lg font-medium hover:bg-gray-800 transition-colors inline-flex items-center gap-2 disabled:opacity-60 disabled:cursor-not-allowed cursor-pointer"
          >
            <span>⬆️</span>
            {status === "uploading" ? "Uploading..." : "Upload Image"}
          </button>
        )}
      </div>

      {/* Status + server result, still inside the card */}
      <div className="mt-4">
        {status === "done" &&
          serverResult &&
          "ok" in serverResult &&
          serverResult.ok && (
            <div className="text-left text-xs md:text-sm bg-gray-50 border rounded-lg p-3 text-black">
              <div>
                <span className="font-semibold">Server accepted!</span>
              </div>
              <div>
                <span className="font-semibold">Name:</span> {serverResult.name}
              </div>
              <div>
                <span className="font-semibold">Type:</span> {serverResult.type}
              </div>
              <div>
                <span className="font-semibold">Size:</span>{" "}
                {Math.round(serverResult.size / 1024)} KB
              </div>
            </div>
          )}

        {status === "error" && error && (
          <div className="text-sm text-red-600">{error}</div>
        )}
      </div>
    </div>
  );
}
