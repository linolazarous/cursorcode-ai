import { NextResponse } from "next/server";

export async function POST(request: Request) {
  try {
    const body = await request.json();

    // Forward to backend monitoring endpoint
    const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/monitoring/log-error`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        // Forward auth cookie if user is logged in
        Cookie: request.headers.get("cookie") || "",
      },
      body: JSON.stringify(body),
    });

    if (!res.ok) throw new Error("Backend logging failed");

    return NextResponse.json({ status: "logged" });
  } catch (err) {
    console.error("Frontend monitoring failed:", err);
    return NextResponse.json({ status: "error" }, { status: 500 });
  }
}
