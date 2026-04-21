import { NextRequest, NextResponse } from "next/server";
import { isAuthorizedControlPlaneWrite } from "@/lib/control-plane-auth";
import { fetchControlPlaneJson } from "@/lib/control-plane-client";
import { getControlPlaneUrl } from "@/lib/config";
import { submitTrainingLocally } from "@/lib/dashboard-actions";

export const runtime = "nodejs";

export async function POST(request: NextRequest) {
  if (!isAuthorizedControlPlaneWrite(request)) {
    return NextResponse.json({ error: "control-plane authentication failed" }, { status: 401 });
  }
  const payload = (await request.json()) as {
    requestId?: string;
    executorRef?: string;
    candidateOut?: string;
  };
  if (!payload.requestId) {
    return NextResponse.json({ error: "requestId is required" }, { status: 400 });
  }
  const resolvedPayload = {
    requestId: payload.requestId,
    executorRef: payload.executorRef,
    candidateOut: payload.candidateOut
  };
  try {
    const result = getControlPlaneUrl()
      ? await fetchControlPlaneJson<Record<string, unknown>>(
          "/api/training/submit",
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(resolvedPayload)
          },
          { requireAuth: true }
        )
      : await submitTrainingLocally(resolvedPayload);
    return NextResponse.json(result);
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "submit training failed" },
      { status: 500 }
    );
  }
}
