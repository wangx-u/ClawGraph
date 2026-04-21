import { NextRequest, NextResponse } from "next/server";
import { isAuthorizedControlPlaneWrite } from "@/lib/control-plane-auth";
import { fetchControlPlaneJson } from "@/lib/control-plane-client";
import { getControlPlaneUrl } from "@/lib/config";
import { reviewOverrideLocally } from "@/lib/dashboard-actions";

export const runtime = "nodejs";

export async function POST(request: NextRequest) {
  if (!isAuthorizedControlPlaneWrite(request)) {
    return NextResponse.json({ error: "control-plane authentication failed" }, { status: 401 });
  }
  const payload = (await request.json()) as {
    sessionId?: string;
    runId?: string;
    feedbackId?: string;
    reviewNote?: string;
  };
  if (!payload.sessionId || !payload.runId) {
    return NextResponse.json({ error: "sessionId and runId are required" }, { status: 400 });
  }
  try {
    const result = getControlPlaneUrl()
      ? await fetchControlPlaneJson<Record<string, unknown>>(
          "/api/dashboard/feedback/review-override",
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
          },
          { requireAuth: true }
        )
      : await reviewOverrideLocally({
          sessionId: payload.sessionId,
          runId: payload.runId,
          feedbackId: payload.feedbackId,
          reviewNote: payload.reviewNote
        });
    return NextResponse.json(result);
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "review override failed" },
      { status: 500 }
    );
  }
}
