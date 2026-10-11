# 官方插件目录(Official Plugins)

本目录是 **AgentPlatform 官方插件**的家。官方插件在本仓库维护、随仓库 CI 校验,
但**与平台核心严格分层**——官方不等于内建:

- 平台只提供域无关机制:注册表、调度、通知、多模态、ContentBlocks、存储原语;
- 领域 schema、领域 @tool、领域算法与 prompt 一律在插件内定义;
- 判定标准:**换一个领域能原样复用的进平台,只有这个领域才需要的进插件**;
- 平台核心代码 diff 中不允许出现任何具体插件的领域词(如 mistake/错题)。

## 目录约定

```
plugins/
├── README.md          # 本文件:分层规则与目录约定
├── study-english/     # 英语学习助手(沪教版高中)
├── study-chinese/     # 语文/文言文助手(沪教版高中)
└── study-math/        # 数学学习助手(沪教版高中)
```

## 官方插件契约

每个官方插件交付/变更时必须满足:

1. `agentplatform validate` 与 `agentplatform test` 通过;
2. **配套 e2e 旅程**:`web/e2e/journeys.spec.ts` 中有该插件的旅程(助手广场 → 开始对话 →
   真实提问 → 断言技能产出关键内容),`npx playwright test` 全绿——静态校验与单测不能替代;
3. 遵守上方分层规则:平台核心代码 diff 中不出现本插件的领域词。

## 开发与发布

```bash
agentplatform validate plugins/study-english     # 静态校验
agentplatform test plugins/study-english         # 自动化用例
agentplatform deploy plugins/study-english --target http://localhost:8000
```

官方插件随仓库演进,版本号遵循 SemVer;部署后在助手广场可见,可被其他插件经
`depends_on` 复用其 skill/tool。
