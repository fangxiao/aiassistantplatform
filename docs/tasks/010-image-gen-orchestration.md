# 010 · 生图能力与多步编排保障(M18)

基于设计文档拆解,标注依赖与优先级。writewx(微信公众号写作助手)配图需求驱动。

| 编号 | 任务 | 依赖 | 优先级 | 状态 |
|---|---|---|---|---|
| T18.1 | `tool:image_gen` 公共生图工具:OpenAI 兼容 /images/generations,b64 落盘 uploads 经 /api/files/raw 回 URL;凭据缺省复用主网关(零配置);loop 特判 + RESOURCE impl_path 显式声明(双执行路径可达);测试 7 项 | M15(uploads 通道) | P0 | ✅ 2026-09-26 |
| T18.2 | 开发规范 4.1「多步工具编排的模型遵循度」:确定性兜底/降级安全/提示词写法/关键校验不交给模型 | T18.1 | P0 | ✅ 2026-09-26 |
| T18.3 | 平台级"必须调用"步骤编排保障机制(step-wise 执行校验/漏调重试)——涉及 agent loop 架构,**等 writewx 0.5.0 WebUI 实测数据后评估** | T18.2,writewx 实测数据 | P2 | 📋 待裁决 |

## 背景

- writewx 能力咨询(20260926-1231)→ 用户裁决方案 A(平台内置工具,插件零凭据)
- 端侧配图闭环:image_gen 回填 `/api/files/raw` URL → `browser_wechat_draft` 注入草稿 → 公众号编辑器自动转存素材库,免公网托管、免微信凭据
- 缺陷教训:RESOURCE 未声明 impl_path 时种子落 builtin 约定路径,绕过 loop 特判的执行路径(如插件本地 dev CLI)加载失败——**非 loop 特判类内置工具必须显式声明 impl_path**
- 测试教训:裸提示词下模型可能幻觉"工具返回"(编造 JSON,tool_calls=False)——验证工具链路必须强制真实调用并核对落盘证据
