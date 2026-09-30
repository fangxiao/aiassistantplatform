# 技术设计 · 飞书通道(017 · 对应需求 012)

- 文档版本:v0.1
- 日期:2026-09-30
- 流程阶段:阶段 2 · 设计(与需求同轮确认,通道型功能范围收敛)

## 1. 架构

```
飞书开放平台 ──WS 长连接── channel/feishu.py(后台任务,api 容器内)
                                   │ 队列桥(SDK 线程 → call_soon_threadsafe → asyncio)
                                   ▼
                        agent_stream_for_session(与 Web 同源,含 P1 检查点)
                                   │ 汇聚最终文本
                                   ▼
                        im.v1.message.reply(文本回复)
```

## 2. 模块与数据

- `core/channel/feishu.py`:WS 客户端(SDK 线程)、事件分发、per-chat 串行锁、
  命令(/重置 /帮助)、回复封装(SDK sync 调用丢线程池);
- `core/channel/model.py` + 迁移 d8f2a4b6c105:`channel_sessions`
  (channel, chat_id) ↔ session_id,uq(channel, chat_id);
- settings:`feishu_app_id / feishu_app_secret / feishu_default_plugin`;
- lifespan:凭证齐全 `start()`(WS 线程 daemon + asyncio worker),未配置跳过。

## 3. 关键决策

1. **WS 长连接而非回调**:免公网 HTTPS 入口,本地 Docker 即可接;
2. **网关跑在 api 容器内**(后台任务)而非独立服务:trial 复用进程内
   `agent_stream_for_session`(无 HTTP 自调用认证问题);连接独立性与
   水平扩容留 P2(独立 channel-gateway 容器);
3. **共享服务账号**(feishu-channel@…,role=user):P1 极简;每飞书用户
   独立账号留 P2(需求 012 §5);
4. **per-chat 串行锁**:同一飞书会话不并发跑同一平台会话(A4);
   不同会话并行;
5. **纯文本回复**:富组件(表格/表单)不在飞书渲染,回复尾注提示到 Web 端
   操作;富卡片留 P2。

## 4. 附录:飞书开放平台配置(用户操作)

1. https://open.feishu.cn 创建**企业自建应用**,记录 App ID / App Secret;
2. 「添加应用能力」→ 开启**机器人**;
3. 「事件与回调」→ 订阅方式选**长连接**;订阅事件
   `接收消息 im.message.receive_v1`;
4. 「权限管理」开通:获取与发送单聊、群组消息(`im:message`、
   `im:message:send_as_bot`);
5. 发布版本并可用;把 App ID/Secret 配到平台
   (`FEISHU_APP_ID / FEISHU_APP_SECRET`,默认助手可配 `FEISHU_DEFAULT_PLUGIN`);
6. 重启 api 容器,日志出现「飞书通道已启动」;在飞书里搜到机器人直接发消息。
