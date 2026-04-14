"use client";

import { useState } from "react";
import type { GuidedFlow } from "@/lib/types";
import { Card } from "@/components/ui/card";

export function FlowSteps({ flow }: { flow: GuidedFlow }) {
  const [activeIndex, setActiveIndex] = useState(0);
  const activeStep = flow.steps[activeIndex] ?? flow.steps[0];

  return (
    <Card eyebrow="流程向导" title={flow.title} strong>
      <p className="text-sm text-[color:var(--text-muted)]">{flow.description}</p>
      <div className="mt-4 h-2 overflow-hidden rounded-full bg-sky-100">
        <div
          className="h-full rounded-full bg-[linear-gradient(90deg,#3277ff,#16ccb3)] transition-all"
          style={{ width: `${((activeIndex + 1) / flow.steps.length) * 100}%` }}
        />
      </div>
      <div className="mt-6 space-y-4">
        {flow.steps.map((step, index) => (
          <button
            className="flex w-full gap-4 rounded-[1.15rem] p-2 text-left transition hover:bg-sky-50/80"
            key={step.title}
            onClick={() => setActiveIndex(index)}
            type="button"
          >
            <div
              className={
                index === activeIndex
                  ? "flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-sky-200 bg-sky-50 text-sm text-sky-700"
                  : "flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-slate-200 bg-white text-sm text-[color:var(--text-soft)]"
              }
            >
              {index + 1}
            </div>
            <div>
              <div className="font-medium">{step.title}</div>
              <div className="mt-1 text-sm leading-6 text-[color:var(--text-muted)]">{step.detail}</div>
            </div>
          </button>
        ))}
      </div>
      <div className="tech-highlight mt-5 rounded-[1.15rem] p-4">
        <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">现在该做什么</div>
        <div className="mt-2 text-base font-medium">{activeStep.title}</div>
        <p className="mt-2 text-sm leading-6 text-[color:var(--text-muted)]">{activeStep.detail}</p>
      </div>
    </Card>
  );
}
