import { expect, test } from "@playwright/test";

test.describe.configure({ mode: "serial" });

test("首页和接入页展示真实数据口径", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "总览", exact: true })).toBeVisible();
  await expect(page.getByText("任务标签覆盖率")).toBeVisible();
  await expect(page.getByText("决策语义覆盖率")).toBeVisible();
  await expect(page.getByText("已生成验证资产")).toBeVisible();
  await expect(page.getByText("任务识别清晰度")).toHaveCount(0);

  await page.goto("/access");

  await expect(page.getByRole("heading", { name: "接入", exact: true })).toBeVisible();
  await expect(page.getByText("当前使用本地 ClawGraph Store").first()).toBeVisible();
  await expect(page.getByText("请求归属清晰度")).toBeVisible();
  await expect(page.getByText("任务标签覆盖率")).toBeVisible();
  await expect(page.getByText("决策语义覆盖率")).toBeVisible();
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

test("人工复核可以在 Web 内完成确认和关闭", async ({ page }) => {
  await page.goto("/feedback");

  const card = page
    .getByText("需要人工确认该轨迹是否可进入训练集")
    .locator("xpath=ancestor::section[1]")
    .first();

  await expect(card).toBeVisible();
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
