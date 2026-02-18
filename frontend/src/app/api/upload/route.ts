import { NextResponse } from "next/server";

const ALLOWED_TYPES = new Set(["image/jpeg", "image/png"]);
const MAX_MB = 8;
const MAX_BYTES = MAX_MB * 1024 * 1024;

export async function POST(req: Request) {
  const formData = await req.formData();
  const file = formData.get("file");

  if (!(file instanceof File)) {
    return NextResponse.json({ error: "No file uploaded" }, { status: 400 });
  }

  if (!ALLOWED_TYPES.has(file.type)) {
    return NextResponse.json(
      { error: "Invalid file type. Use JPEG, PNG, or WebP." },
      { status: 415 },
    );
  }

  if (file.size > MAX_BYTES) {
    return NextResponse.json(
      { error: `File too large. Max is ${MAX_MB}MB.` },
      { status: 413 },
    );
  }

  // TODO: Forward to FastAPI next
  return NextResponse.json({
    ok: true,
    name: file.name,
    type: file.type,
    size: file.size,
  });
}
