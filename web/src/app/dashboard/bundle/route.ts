import { NextResponse } from "next/server";
import { fetchControlPlaneJson } from "@/lib/control-plane-client";
import { getControlPlaneUrl, getStoreUri } from "@/lib/config";
import { loadLocalProdBundle } from "@/lib/local-prod-bridge";

export const runtime = "nodejs";

export async function GET() {
  if (getControlPlaneUrl()) {
    try {
      const payload = await fetchControlPlaneJson<{
        bundle: Record<string, unknown>;
        meta?: Record<string, unknown>;
      }>("/api/dashboard/bundle");
      return NextResponse.json(payload);
    } catch (error) {
      return NextResponse.json(
        {
          error: error instanceof Error ? error.message : "Failed to fetch bundle from control-plane."
        },
        { status: 502 }
      );
    }
  }

  const storeUri = getStoreUri();
  if (!storeUri) {
    return NextResponse.json(
      {
        error: "CLAWGRAPH_STORE_URI is required for the first-party dashboard API."
      },
      { status: 503 }
    );
  }

  const bundle = await loadLocalProdBundle(storeUri);
  if (!bundle) {
    return NextResponse.json(
      {
        error: "Failed to build dashboard bundle from the configured store."
      },
      { status: 500 }
    );
  }

  return NextResponse.json({
    bundle,
    meta: {
      provider: "remote-http",
      status: "prod",
      statusText: "当前使用首方 Dashboard HTTP API",
      supportsMutations: true
    }
  });
}
