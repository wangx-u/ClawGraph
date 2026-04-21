"use server";

import { revalidatePath } from "next/cache";
import {
  bootstrapReviewAction as bootstrapReviewInStore,
  resolveFeedbackAction as resolveFeedbackInStore,
  reviewOverrideAction as reviewOverrideInStore,
  syncFeedbackQueueAction as syncFeedbackQueueInStore
} from "@/lib/dashboard-actions";

function revalidateDashboardViews(sessionId?: string, runId?: string) {
  const paths = new Set([
    "/",
    "/access",
    "/feedback",
    "/sessions",
    "/supervision",
    "/training",
    "/coverage",
    "/datasets",
    "/evaluation",
    "/curation/cohorts",
    "/curation/candidates"
  ]);
  if (sessionId) {
    paths.add(`/sessions/${sessionId}`);
    if (runId) {
      paths.add(`/sessions/${sessionId}/runs/${runId}/replay`);
    }
  }
  paths.forEach((path) => revalidatePath(path));
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
  revalidateDashboardViews(sessionId, runId);
}

export async function syncRunFeedbackQueue(formData: FormData) {
  const sliceId = String(formData.get("sliceId") ?? "");
  const sessionId = String(formData.get("sessionId") ?? "");
  const runId = String(formData.get("runId") ?? "");
  if (!sliceId || !sessionId || !runId) {
    throw new Error("sliceId, sessionId and runId are required");
  }
  await syncFeedbackQueueInStore({
    sliceId,
    sessionId,
    runId,
    source: "dashboard.review_sync",
    purpose: "replay_review"
  });
  revalidateDashboardViews(sessionId, runId);
}

export async function bootstrapReplayGovernance(formData: FormData) {
  const sessionId = String(formData.get("sessionId") ?? "");
  const runId = String(formData.get("runId") ?? "");
  if (!sessionId || !runId) {
    throw new Error("sessionId and runId are required");
  }
  await bootstrapReviewInStore({
    sessionId,
    runId,
    source: "dashboard.review_sync",
    purpose: "replay_review"
  });
  revalidateDashboardViews(sessionId, runId);
}
