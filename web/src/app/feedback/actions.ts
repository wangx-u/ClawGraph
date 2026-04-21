"use server";

import { revalidatePath } from "next/cache";
import {
  resolveFeedbackAction as resolveFeedbackInStore,
  reviewOverrideAction as reviewOverrideInStore
} from "@/lib/dashboard-actions";

function revalidateDashboardViews() {
  [
    "/",
    "/access",
    "/feedback",
    "/datasets",
    "/evaluation",
    "/curation/cohorts",
    "/curation/candidates"
  ].forEach((path) => revalidatePath(path));
}

export async function markFeedbackReviewed(formData: FormData) {
  const feedbackId = String(formData.get("feedbackId") ?? "");
  if (!feedbackId) {
    throw new Error("feedbackId is required");
  }
  await resolveFeedbackInStore({
    feedbackId,
    status: "reviewed",
    note: "已在 Dashboard 中人工确认。"
  });
  revalidateDashboardViews();
}

export async function resolveFeedback(formData: FormData) {
  const feedbackId = String(formData.get("feedbackId") ?? "");
  if (!feedbackId) {
    throw new Error("feedbackId is required");
  }
  await resolveFeedbackInStore({
    feedbackId,
    status: "resolved",
    note: "已在 Dashboard 中关闭回流项。"
  });
  revalidateDashboardViews();
}

export async function confirmRunByHuman(formData: FormData) {
  const sessionId = String(formData.get("sessionId") ?? "");
  const runId = String(formData.get("runId") ?? "");
  if (!sessionId || !runId) {
    throw new Error("sessionId and runId are required");
  }
  const feedbackId = String(formData.get("feedbackId") ?? "") || undefined;
  await reviewOverrideInStore({
    sessionId,
    runId,
    feedbackId,
    reviewNote: "已在 Dashboard 中人工确认，可进入数据集或验证流程。"
  });
  revalidateDashboardViews();
}
