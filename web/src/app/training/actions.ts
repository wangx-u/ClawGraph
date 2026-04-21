"use server";

import { revalidatePath } from "next/cache";
import {
  createHandoffAction,
  evaluateCandidateAction,
  submitTrainingAction
} from "@/lib/dashboard-actions";

function revalidateTrainingViews() {
  [
    "/training",
    "/evaluation",
    "/coverage",
    "/datasets"
  ].forEach((path) => revalidatePath(path));
}

export async function submitTrainingRequest(formData: FormData) {
  const requestId = String(formData.get("requestId") ?? "");
  if (!requestId) {
    throw new Error("requestId is required");
  }
  await submitTrainingAction({ requestId });
  revalidateTrainingViews();
  revalidatePath(`/training/requests/${requestId}`);
}

export async function evaluateTrainingCandidate(formData: FormData) {
  const candidateId = String(formData.get("candidateId") ?? "");
  const evalSuiteId = String(formData.get("evalSuiteId") ?? "") || undefined;
  const baselineModel = String(formData.get("baselineModel") ?? "") || undefined;
  if (!candidateId) {
    throw new Error("candidateId is required");
  }
  await evaluateCandidateAction({
    candidateId,
    evalSuiteId,
    baselineModel
  });
  revalidateTrainingViews();
  revalidatePath(`/training/candidates/${candidateId}`);
}

export async function createTrainingHandoff(formData: FormData) {
  const candidateId = String(formData.get("candidateId") ?? "");
  const promotionDecisionId = String(formData.get("promotionDecisionId") ?? "") || undefined;
  if (!candidateId) {
    throw new Error("candidateId is required");
  }
  await createHandoffAction({
    candidateId,
    promotionDecisionId
  });
  revalidateTrainingViews();
  revalidatePath(`/training/candidates/${candidateId}`);
}
