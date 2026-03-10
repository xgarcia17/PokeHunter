"use client";

import { useRef, useState, type ChangeEvent } from "react";

type AddCollectionResponse =
  | {
      ok: true;
      cardId: string;
      userId: string;
      quantity: number;
      pricingWarning?: string | null;
      card: {
        id: string;
        name: string;
        set_id: string;
        number: string;
        price_usd: number | null;
        price_last_updated: string | null;
      };
    }
  | {
      ok?: false;
      error: string;
    };

type AddedCard = Extract<AddCollectionResponse, { ok: true }>["card"];

type UploadResponse =
  | {
      ok: true;
      name: string;
      type: string;
      size: number;
      identify: {
        score: number;
        card_id: string | null;
        set_id: string | null;
        card_number: string | null;
        card_name: string | null;
        matched_storage_path: string | null;
        matched_image_url: string | null;
      };
    }
  | {
      ok?: false;
      error: string;
    };

async function addToCollection(
  userId: string,
  cardId: string,
): Promise<AddCollectionResponse> {
  const res = await fetch("/api/collections/add", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ userId, cardId }),
  });

  let data: AddCollectionResponse | null = null;
  try {
    data = (await res.json()) as AddCollectionResponse;
  } catch {
    // ignore
  }

  if (!res.ok) {
    const msg = data && "error" in data ? data.error : "Could not add card";
    throw new Error(msg);
  }

  return data as AddCollectionResponse;
}

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

  let data: UploadResponse | null = null;
  try {
    data = await res.json();
  } catch {
    // ignore
  }

  if (!res.ok) {
    const msg = data && "error" in data ? data.error : `Upload failed (${res.status})`;
    throw new Error(msg);
  }

  return data as UploadResponse;
}

type ScannerProps = {
  userId: string;
};

export default function Scanner({ userId }: ScannerProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);

  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [status, setStatus] = useState<"idle" | "uploading" | "done" | "error">(
    "idle",
  );
  const [error, setError] = useState<string | null>(null);
  const [serverResult, setServerResult] = useState<UploadResponse | null>(null);
  const [addStatus, setAddStatus] = useState<"idle" | "adding" | "done" | "error">(
    "idle",
  );
  const [addMessage, setAddMessage] = useState<string | null>(null);
  const [addedCard, setAddedCard] = useState<AddedCard | null>(null);

  function formatPrice(price: number | null) {
    if (price === null) return "N/A";
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
    }).format(price);
  }

  function formatTimestamp(value: string | null) {
    if (!value) return "N/A";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;

    return new Intl.DateTimeFormat("en-US", {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(date);
  }

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
    setAddStatus("idle");
    setAddMessage(null);
    setAddedCard(null);

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
    setAddStatus("idle");
    setAddMessage(null);
    setAddedCard(null);
    setPreviewUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return null;
    });
  }

  async function onAddToCollection() {
    if (!serverResult || !("ok" in serverResult) || !serverResult.ok) return;
    const cardId = serverResult.identify.card_id;
    if (!cardId) {
      setAddStatus("error");
      setAddMessage("No detected card id to add.");
      return;
    }

    setAddStatus("adding");
    setAddMessage(null);

    try {
      const result = await addToCollection(userId, cardId);
      if ("ok" in result && result.ok) {
        setAddStatus("done");
        setAddedCard(result.card);
        setAddMessage(
          result.pricingWarning
            ? `Added to collection. Quantity: ${result.quantity}. Pricing unavailable right now.`
            : `Added to collection. Quantity: ${result.quantity}`,
        );
      }
    } catch (e) {
      setAddStatus("error");
      setAddMessage(
        e instanceof Error ? e.message : "Failed to add to collection",
      );
    }
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

        {/* Only show the "Upload Image" button when there is NO preview */}
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
            <div className="text-left text-xs md:text-sm bg-gray-50 border rounded-lg p-3 text-black space-y-4">
              <div className="font-semibold">Card identification result</div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <div className="font-medium mb-1">Uploaded</div>
                  {previewUrl && (
                    <img
                      src={previewUrl}
                      alt="Uploaded card"
                      className="max-h-72 w-auto rounded-lg border bg-white"
                    />
                  )}
                </div>

                <div>
                  <div className="font-medium mb-1">Detected from Supabase</div>
                  {serverResult.identify.matched_image_url ? (
                    <img
                      src={serverResult.identify.matched_image_url}
                      alt="Detected card from Supabase"
                      className="max-h-72 w-auto rounded-lg border bg-white"
                    />
                  ) : (
                    <div className="text-gray-500">No matched image found.</div>
                  )}
                </div>
              </div>

              <div>
                <span className="font-semibold">Detected card:</span>{" "}
                {serverResult.identify.card_name ?? "Unknown"}
              </div>
              <div>
                <span className="font-semibold">Set / Number:</span>{" "}
                {serverResult.identify.set_id ?? "?"} /{" "}
                {serverResult.identify.card_number ?? "?"}
              </div>
              <div>
                <span className="font-semibold">Confidence:</span>{" "}
                {(serverResult.identify.score * 100).toFixed(2)}%
              </div>

              <div className="pt-1">
                <button
                  type="button"
                  onClick={onAddToCollection}
                  disabled={
                    addStatus === "adding" || !serverResult.identify.card_id
                  }
                  className="bg-gray-900 text-white px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-60 disabled:cursor-not-allowed"
                >
                  {addStatus === "adding" ? "ADDING..." : "ADD TO COLLECTION"}
                </button>
                {addMessage && (
                  <div
                    className={`mt-2 text-sm ${addStatus === "error" ? "text-red-600" : "text-green-700"}`}
                  >
                    {addMessage}
                  </div>
                )}
                {addedCard && (
                  <div className="mt-3 text-sm text-gray-800 space-y-1">
                    <div>
                      <span className="font-semibold">Live price:</span>{" "}
                      {formatPrice(addedCard.price_usd)}
                    </div>
                    <div>
                      <span className="font-semibold">Price last updated:</span>{" "}
                      {formatTimestamp(addedCard.price_last_updated)}
                    </div>
                  </div>
                )}
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
