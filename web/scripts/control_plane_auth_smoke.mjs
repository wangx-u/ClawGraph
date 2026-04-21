#!/usr/bin/env node

const baseUrl = (process.env.CLAWGRAPH_API_TEST_BASE_URL || "http://127.0.0.1:3402").replace(/\/$/, "");
const endpoint = `${baseUrl}/dashboard/feedback/resolve`;
const token = process.env.CLAWGRAPH_CONTROL_PLANE_TOKEN || "";

async function post(headers = {}) {
  const response = await fetch(endpoint, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...headers
    },
    body: JSON.stringify({
      feedbackId: "fb_smoke_auth",
      status: "resolved",
      note: "auth smoke"
    })
  });
  const payload = await response.json().catch(() => ({}));
  return { status: response.status, payload };
}

const unauthorized = await post();
if (unauthorized.status !== 401) {
  console.error(JSON.stringify({
    ok: false,
    check: "unauthorized-write",
    expected: 401,
    actual: unauthorized.status,
    payload: unauthorized.payload
  }, null, 2));
  process.exit(1);
}

if (!token) {
  console.log(JSON.stringify({
    ok: true,
    check: "unauthorized-write",
    unauthorizedStatus: unauthorized.status,
    note: "authorized smoke skipped because CLAWGRAPH_CONTROL_PLANE_TOKEN is not set"
  }, null, 2));
  process.exit(0);
}

const authorized = await post({ Authorization: `Bearer ${token}` });
if (authorized.status === 401) {
  console.error(JSON.stringify({
    ok: false,
    check: "authorized-write",
    expected: "non-401",
    actual: authorized.status,
    payload: authorized.payload
  }, null, 2));
  process.exit(1);
}

console.log(JSON.stringify({
  ok: true,
  check: "auth-boundary",
  unauthorizedStatus: unauthorized.status,
  authorizedStatus: authorized.status,
  authorizedPayload: authorized.payload
}, null, 2));
