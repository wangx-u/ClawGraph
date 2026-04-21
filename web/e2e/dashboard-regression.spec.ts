import { expect, test } from "@playwright/test";

test.describe.configure({ mode: "serial" });

test("首页和接入页展示真实数据口径", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "闭环控制台", exact: true })).toBeVisible();
  await expect(page.getByText("学习数据与模型接替控制面")).toBeVisible();
  await expect(page.getByRole("heading", { name: "第 4 步 · 人工筛选" }).first()).toBeVisible();
  await expect(page.getByText("全链路现在进行到哪")).toBeVisible();
  await expect(page.getByText("切片替代机会")).toBeVisible();
  await expect(page.getByText("任务识别清晰度")).toHaveCount(0);

  await page.goto("/access");

  await expect(page.getByRole("heading", { name: "接入", exact: true })).toBeVisible();
  await expect(page.getByText("当前使用首方 Dashboard HTTP API").first()).toBeVisible();
  await expect(page.getByText("请求归属清晰度")).toBeVisible();
  await expect(page.getByText("任务标签覆盖率")).toBeVisible();
  await expect(page.getByText("决策语义覆盖率")).toBeVisible();
  await expect(page.getByText("SQLFluff #1625").first()).toBeVisible();
});

test("Session 和 Replay 页面优先展示任务标题、步骤类型和自动摘要", async ({ page }) => {
  await page.goto("/sessions/session_train_e2e");

  await expect(page.locator("h1", { hasText: "SQLFluff #1625" })).toBeVisible();
  await expect(page.getByText(/会话 session_…in_e2e/)).toBeVisible();
  await expect(page.getByText("可筛选").first()).toBeVisible();
  await expect(page.getByText("待复核").first()).toBeVisible();
  await expect(page.getByText("运行 run_train_e2e")).toBeVisible();

  await page.goto("/sessions/session_train_e2e/runs/run_train_e2e/replay");

  await expect(page.locator("h1", { hasText: "回放 SQLFluff #1625" })).toBeVisible();
  await expect(page.getByText("模型推理").first()).toBeVisible();
  await expect(page.getByText("对话推理").first()).toBeVisible();
  await expect(page.getByText("Fix sqlfluff issue 1625").first()).toBeVisible();
});

test("数据集、批次和评测详情页展示真实 manifest 字段", async ({ page }) => {
  await page.goto("/datasets/ds_e2e_sft");

  await expect(page.locator("h1", { hasText: "SFT · SQLFluff 训练批次" })).toBeVisible();
  await expect(page.getByText("Taxonomy 版本：benchmark.swebench.v1")).toBeVisible();
  await expect(page.getByText("切分策略：Seed Guard · train 1 / val 0 / test 0")).toBeVisible();
  await expect(page.getByText("批次约束：Training · 质量 >= 0.90 · 验证 >= 0.90")).toBeVisible();
  await expect(page.getByText("待补充")).toHaveCount(0);

  await page.goto("/curation/cohorts/cohort_train_e2e");

  await expect(page.locator("h1", { hasText: "SQLFluff 训练批次" })).toBeVisible();
  await expect(
    page.getByText("覆盖任务：Benchmark Coding Task / Swebench Issue Fix")
  ).toBeVisible();
  await expect(
    page.getByText("筛选规则：Benchmark Coding Task / Swebench Issue Fix · 来源 Benchmark Swebench Lite")
  ).toBeVisible();
  await expect(page.getByText("质量门槛：质量 >= 0.90 · 验证 >= 0.90")).toBeVisible();
  await expect(page.getByText("待补充")).toHaveCount(0);

  await page.goto("/evaluation/eval_e2e_offline");

  await expect(page.locator("h1", { hasText: "SQLFluff 离线验证" })).toBeVisible();
  await expect(
    page.getByText("Benchmark Coding Task / Swebench Issue Fix").first()
  ).toBeVisible();
  await expect(page.getByText("mini-e2e vs teacher-e2e").first()).toBeVisible();
  await expect(page.getByText("通过").first()).toBeVisible();
});

test("训练资产与覆盖策略页面展示真实候选链路和 rollback 条件", async ({ page }) => {
  await page.goto("/training");

  await expect(page.locator("h1", { hasText: "模型接替工作区" })).toBeVisible();
  await expect(page.getByText("把训练请求、候选模型、固定评测、放量决策和交接状态串成一条接替链路")).toBeVisible();
  await expect(page.getByText("AIOps 候选模型 v1")).toHaveCount(0);
  await expect(page.getByText("mini-e2e", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("当前模型接替概览")).toBeVisible();
  await expect(page.getByText("已关联请求")).toBeVisible();

  await page.goto("/training/requests/train_e2e_sft");
  await expect(page.locator("h1", { hasText: "SFT · SQLFluff 训练批次" })).toBeVisible();
  await expect(page.getByText("候选模型 1 个 · 评测执行 1 个 · 交接包 1 个")).toBeVisible();

  await page.goto("/training/candidates/cand_e2e_sft");
  await expect(page.locator("h1", { hasText: "mini-e2e" })).toBeVisible();
  await expect(page.getByText("输出状态：已发布，可进入替换评估")).toBeVisible();

  await page.goto("/training/evaluations/evalexec_e2e_sft");
  await expect(page.locator("h1", { hasText: "benchmark-grader · 1 个样本" })).toBeVisible();
  await expect(page.getByText("放量决策：promote · canary")).toBeVisible();

  await page.goto("/training/handoffs/handoff_e2e_sft");
  await expect(page.locator("h1", { hasText: "canary · promote" })).toBeVisible();
  await expect(page.getByText("Route Mode")).toBeVisible();
  await expect(page.getByText("当前决策", { exact: true })).toBeVisible();
  await page.getByText("查看技术明细").click();
  await expect(page.getByText("\"baseline_model\": \"teacher-e2e\"")).toBeVisible();
  await expect(page.getByText("\"route_mode\": \"canary\"")).toBeVisible();

  await page.goto("/coverage");

  await expect(page.locator("h1", { hasText: "上线控制面" })).toBeVisible();
  await expect(page.getByText("现在可执行")).toBeVisible();
  await expect(page.getByText("切流矩阵")).toBeVisible();
  await expect(page.getByText("verifier_pass_rate_drop > 0.03")).toBeVisible();
  await expect(page.getByText("fallback_rate > 0.10")).toBeVisible();
});

test("人工复核可以通过首方 HTTP API 在 Web 内完成确认和关闭", async ({ page }) => {
  await page.goto("/feedback");

  const card = page
    .getByText("需要人工确认该轨迹是否可进入训练集")
    .locator("xpath=ancestor::section[1]")
    .first();

  await expect(card).toBeVisible();
  await expect(page.getByText("此数据源暂为只读")).toHaveCount(0);
  await expect(
    card.getByText("Benchmark Coding Task / Swebench Issue Fix").first()
  ).toBeVisible();

  await card.getByRole("button", { name: "人工确认并入池" }).click();

  await expect(
    card.getByText("已在 Dashboard 中人工确认，可进入数据集或验证流程。")
  ).toBeVisible();
  await expect(card.getByText("已关闭")).toBeVisible();

  await page.reload();
  await expect(page.locator("section", { hasText: "待处理" }).first()).toContainText("0");
  await expect(page.locator("section", { hasText: "已关闭" }).first()).toContainText("1");
});
