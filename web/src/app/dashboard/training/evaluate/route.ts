import { NextRequest, NextResponse } from "next/server";
import { isAuthorizedControlPlaneWrite } from "@/lib/control-plane-auth";
import { fetchControlPlaneJson } from "@/lib/control-plane-client";
import { getControlPlaneUrl } from "@/lib/config";
import { evaluateCandidateLocally } from "@/lib/dashboard-actions";

export const runtime = "nodejs";

export async function POST(request: NextRequest) {
  if (!isAuthorizedControlPlaneWrite(request)) {
    return NextResponse.json({ error: "control-plane authentication failed" }, { status: 401 });
  }
  const payload = (await request.json()) as {
    candidateId?: string;
    evalSuiteId?: string;
    baselineModel?: string;
  };
  if (!payload.candidateId) {
    return NextResponse.json({ error: "candidateId is required" }, { status: 400 });
  }
  const resolvedPayload = {
    candidateId: payload.candidateId,
    evalSuiteId: payload.evalSuiteId,
    baselineModel: payload.baselineModel
  };
  try {
    const result = getControlPlaneUrl()
      ? await fetchControlPlaneJson<Record<string, unknown>>(
          "/api/training/evaluate",
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(resolvedPayload)
          },
          { requireAuth: true }
        )
      : await evaluateCandidateLocally(resolvedPayload);
    return NextResponse.json(result);
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "evaluate candidate failed" },
      { status: 500 }
    );
  }
}
