# 任务 · 多模态输入(M16 · 设计 012 精简合并)

| ID | 任务 | 状态 |
|----|------|------|
| T16.1 | 后端:SendMessage.images 校验(≤4 张/单张 5MB/data:image)+ save_user_message 多块 + agent 链路多部分 content(text+image_url)+ 含图模型路由(multimodal_model) | ✅ |
| T16.2 | 前端:Composer 📎/粘贴/预览/移除 + chat.ts sendMessage images + 用户气泡图片渲染(ImageRenderer 复用) | ✅ |
| T16.3 | 测试(9 例):多部分 content/历史不含图/块结构/校验 422/SSE 通;设计 012 | ✅ |
| T16.4 | 对象存储化(dataURL → 服务端文件 URL)、多轮图上下文、语音输入 | ⏳ 后续 |
