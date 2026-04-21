import { NextRequest, NextResponse } from "next/server";
import { isAuthorizedControlPlaneWrite } from "@/lib/control-plane-auth";
import { fetchControlPlaneJson } from "@/lib/control-plane-client";
import { getControlPlaneUrl } from "@/lib/config";
import { resolveFeedbackLocally } from "@/lib/dashboard-actions";

export const runtime = "nodejs";

export async function POST(request: NextRequest) {
  if (!isAuthorizedControlPlaneWrite(request)) {
    return NextResponse.json({ error: "control-plane authentication failed" }, { status: 401 });
  }
  const payload = (await request.json()) as {
    feedbackId?: string;
    status?: "reviewed" | "resolved";
    note?: string;
  };
  if (!payload.feedbackId) {
    return NextResponse.json({ error: "feedbackId is required" }, { status: 400 });
  }
  if (payload.status !== "reviewed" && payload.status !== "resolved") {
    return NextResponse.json({ error: "status must be reviewed or resolved" }, { status: 400 });
  }
  try {
    const result = getControlPlaneUrl()
      ? await fetchControlPlaneJson<Record<string, unknown>>(
          "/api/dashboard/feedback/resolve",
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
          },
          { requireAuth: true }
        )
      : await resolveFeedbackLocally({
          feedbackId: payload.feedbackId,
          status: payload.status,
          note: payload.note
        });
    return NextResponse.json(result);
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "resolve feedback failed" },
      { status: 500 }
    );
  }
}
