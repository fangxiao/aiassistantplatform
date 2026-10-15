# 我的知识库与「我的文件」(20261015)

## 背景与需求

试用反馈:用户上传的附件散落在会话里,无法沉淀复用。需求:
1. 用户可见自己上传过的全部文件(「我的文件」面板)
2. 一键转存知识库(公共库或个人库)
3. 个人库**全局默认挂载**——用户的每个会话、任何助手都自动可检索(20261014 用户裁决)

## 设计

### 数据模型

- 新表 `user_files`(迁移 a1b2c3d4e5f6):每次 /files/upload 落一行(user_id/path/name/size/mime);历史文件从消息块回填
- `knowledge_bases.personal_default` boolean + **partial unique index(owner_id WHERE personal_default)**:每用户至多一个默认个人库,数据库层兜底

### 关键决策

| 决策 | 结论 | 理由 |
|---|---|---|
| 默认挂载语义 | 全局生效,知识库侧可关 | 用户裁决「以后每次都可以使用」 |
| 授权链并入点 | `resolve_allowed_kb_ids` 第四来源(owner==session_user 且 personal_default) | 单一授权收敛点(008 §3.3),防御过滤补「owner 本人可读 private」分支 |
| 个人库创建 | 入库时惰性建「我的知识库」(private, personal_default=true) | 免去独立建库步骤;partial index 保证唯一 |
| 入库文件流 | 服务端直读 uploads 本地文件,不经二次上传 | 复用 `kb_service.add_document` + pipeline;hash 去重沿用 |
| xlsx 解析 | openpyxl 经 BytesIO | KB 管道以无扩展名 doc-id 存文件,openpyxl 按后缀校验会误拒 |

### API

- `GET /files/mine` — 我的文件列表(签名 URL 直出)
- `POST /files/{id}/ingest {kb_id?}` — 入库;kb_id 空则建/复用个人默认库;文件名三级兜底(原名→路径后缀→mime 映射)
- `POST /kb/{id}/personal-default {on}` — 自动挂载开关(仅 owner;开启时清本人其他默认)

### 前端

- 工作台「📁 我的文件」卡(汇总 5 条)+ `/files` 专属页(全量);入库弹窗选个人库/公共库
- 工作台汇总化:各中心卡限 5 条 + 「查看全部」跳专属页(/sessions /scheduler /todos /files)
- 白牌页「我的」抽屉:轻注册用户的个人空间(我的文件/待办),保持纯聊天定位

## 相关修复(同日)

- Word/Excel 附件:对话附件与 KB 双通道支持 docx/xlsx(python-docx/openpyxl 入 pyproject,uv.lock 重锁)
- M37 画像缺口:personas 为空的工作台无定时任务卡,且 PersonaSelect 弹窗遮挡;e2e 助手写 localStorage 须带 personas(20261015 e2e 实测)
- 分享桥接(方案 A):分享页 → 白牌页轻注册,访客获得自己的工作台

## 遗留

- auto 网关概率路由死通道(glm-5.3-flash 502)——外部依赖,已升级网关团队;恢复后补跑 e2e 旅程 3/9/12-14
- 模型对 output_block 下发的遵从度不稳定(markdown 表格代替组件)——人肉测试 A 组观察项
