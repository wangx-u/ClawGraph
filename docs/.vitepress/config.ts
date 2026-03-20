import { defineConfig } from "vitepress";

export default defineConfig({
  title: "ClawGraph",
  description:
    "Immutable, branch-aware execution graphs for OpenClaw-style agents.",
  themeConfig: {
    logo: "/clawgraph-logo.png",
    nav: [
      { text: "Start Here", link: "/guides/start_here" },
      { text: "Guides", link: "/guides/quickstart" },
      { text: "中文", link: "/zh-CN/README" },
      { text: "Examples", link: "/guides/examples" },
      { text: "Concepts", link: "/concepts/execution_facts" },
      { text: "Reference", link: "/reference/cli_reference" }
    ],
    sidebar: {
      "/overview/": [
        {
          text: "Overview",
          items: [
            { text: "What is ClawGraph", link: "/overview/what_is_clawgraph" },
            { text: "Architecture", link: "/overview/architecture" },
            { text: "Why Not Tracing", link: "/overview/why_not_tracing" },
            { text: "Roadmap", link: "/overview/roadmap" }
          ]
        }
      ],
      "/concepts/": [
        {
          text: "Core Concepts",
          items: [
            { text: "Execution Facts", link: "/concepts/execution_facts" },
            { text: "Execution Graph", link: "/concepts/execution_graph" },
            { text: "Branching", link: "/concepts/branching" },
            { text: "Artifact Protocol", link: "/concepts/artifact_protocol" },
            { text: "Semantic Contract", link: "/concepts/semantic_contract" },
            { text: "Supervision Model", link: "/concepts/supervision_model" }
          ]
        }
      ],
      "/guides/": [
        {
          text: "Get Started",
          items: [
            { text: "Start Here", link: "/guides/start_here" },
            { text: "15-Minute Path", link: "/guides/fifteen_minute_path" },
            { text: "Quickstart", link: "/guides/quickstart" },
            { text: "Examples", link: "/guides/examples" },
            { text: "User Stories", link: "/guides/user_stories" },
            { text: "OpenClaw Integration", link: "/guides/openclaw_integration" },
          ]
        },
        {
          text: "Workflows",
          items: [
            { text: "Proxy Mode", link: "/guides/proxy_mode" },
            { text: "Semantic Mode", link: "/guides/semantic_mode" },
            { text: "Replay and Debug", link: "/guides/replay_and_debug" },
            { text: "Dataset Builders", link: "/guides/dataset_builders" },
            { text: "Export to Async RL", link: "/guides/export_to_async_rl" },
            {
              text: "Custom Artifacts and Builders",
              link: "/guides/custom_artifacts_and_builders"
            },
          ]
        }
      ],
      "/zh-CN/": [
        {
          text: "中文入口",
          items: [
            { text: "中文文档", link: "/zh-CN/README" },
            { text: "Start Here", link: "/zh-CN/start_here" },
            { text: "15 分钟路径", link: "/zh-CN/fifteen_minute_path" },
            { text: "接入说明", link: "/zh-CN/openclaw_integration" },
            { text: "数据导出", link: "/zh-CN/dataset_builders" }
          ]
        }
      ],
      "/reference/": [
        {
          text: "Reference",
          items: [
            { text: "Event Protocol", link: "/reference/event_protocol" },
            { text: "Branch Schema", link: "/reference/branch_schema" },
            { text: "Artifact Schema", link: "/reference/artifact_schema" },
            { text: "Semantic Schema", link: "/reference/semantic_schema" },
            { text: "Builder Interface", link: "/reference/builder_interface" },
            { text: "CLI Reference", link: "/reference/cli_reference" },
            { text: "FAQ", link: "/reference/faq" }
          ]
        }
      ]
    },
    socialLinks: [
      { icon: "github", link: "https://github.com/your-org/clawgraph" }
    ],
    footer: {
      message: "Capture once. Reuse everywhere.",
      copyright: "Copyright 2026 ClawGraph Authors"
    },
    search: {
      provider: "local"
    }
  }
});
