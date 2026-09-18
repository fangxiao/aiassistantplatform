# 012 · 多模态输入(对话传图)设计

- 文档版本:v0.1
- 日期:2026-09-18
- 流程阶段:阶段 2 · 设计(精简合并版:需求要点 + 技术方案)
- 背景:对标豆包/WorkBuddy 的多模态输入差距(对比 2026-09-18);平台 multimodal_model
  端点已配置,只差输入链路。

## 1. 需求要点

- U1 对话中**上传或粘贴图片**(最多 4 张,单张 ≤5MB),配文字提问,助手看图回答;
- U2 图片在消息流中正确渲染(用户气泡内缩略图;ImageRenderer 已有);
- U3 含图消息自动路由到**多模态模型**(settings.multimodal_model,默认配置已有);
- U4 历史:图片不重复进后续 LLM 上下文(history 文本化,base64 不膨胀 token);
- U5 校验:非 data:image 前缀拒绝;超限 422。

## 2. 技术方案

```
Composer(📎/粘贴 → dataURL 预览) 
  → sendMessage(sid, content, images[])     POST body images: [dataURL]
  → save_user_message(..., images)          blocks = [markdown?] + [{type:"image",data:{url}}]×n
  → agent_stream_for_session(images 非空 → model=multimodal_model)
  → build_messages(..., images)             最新 user content = 多部分:
                                            [{type:"text"},{type:"image_url",image_url:{url}}...]
  → LLM(OpenAI 兼容 vision)
```

- **存储**:MVP 图片以 dataURL 存消息块(免文件服务;单张 5MB、4 张上限控制膨胀);
  对象存储化留后续(切换时块 data.url 换服务端 URL,渲染不变)。
- **历史**:build_history/message_text 只取 markdown block(现状即安全),图片不进后续
  上下文——设计取舍:省 token,多轮看图以"最新一条含图"为主场景。
- **模型路由**:含图消息 model=multimodal_model(覆盖 manifest 模型——不支持视觉的
  模型传图会直接报错,路由兜底优先)。
- **工具循环**:图片仅进入首轮 user content;tool_call 回填轮次不含图(不再重复发送)。

## 3. 任务

| ID | 内容 |
|----|------|
| T16.1 | SendMessage.images 校验 + save_user_message 多块 + agent 链路多部分 content + 模型路由 |
| T16.2 | Composer 图片选择/粘贴/预览 + chat.ts + 用户气泡图片渲染确认 |
| T16.3 | 测试:校验/save 块/build_messages 多部分/端到端 fake LLM;文档 |
