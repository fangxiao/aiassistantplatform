# AgentPlatform 平台与插件统一样式标准

> 版本 1.0(20261019)· 适用:平台 Web 端(web/)、白牌页、插件 output_block 组件、
> 插件产出的 markdown 正文。本标准从现有实现提炼,新代码必须遵循,存量代码渐进对齐。

## 1. 技术底座

- Tailwind CSS 类名体系(不引入第二套 UI 框架)
- 图标:emoji 体系(📎📊📋📈⏱️📝🔔📁🧩),不引图标库
- 无 dark mode(单主题,浅色)

## 2. 色彩语义(唯一允许的色板)

| 语义 | Tailwind | 用途 |
|---|---|---|
| 主操作/正文强调 | `slate-900`(白底字) | 主按钮、用户消息气泡 |
| 强调/链接/主品牌 | `indigo-600`(hover indigo-700) | 链接、订阅按钮、选中态边框 indigo-300 |
| 页面背景 | `slate-50` | 所有页面根容器 |
| 卡片 | `white` + `border-slate-200` + `shadow-xs` | 所有卡片容器 |
| 成功/完成 | `emerald-50/800`(底) `emerald-600`(字) | 工具完成徽标、成功提示 |
| 失败/危险 | `rose-50/800`;危险按钮 `rose-200/700` | 失败徽标、删除 |
| 进行中/等待 | `amber-50/900` + `animate-pulse` | 加载中徽标 |
| 深度思考 | `violet-50/800` | AI 思考中面板 |
| 辅助文字 | `slate-400`(弱) `slate-500` `slate-600` | 时间戳/说明/次级 |
| 输入框 | `border-slate-300`,focus `border-indigo-500 + ring-1` | 全部输入控件 |

**禁令**:不引入新色系;不写裸色值(一律 Tailwind 类);状态色不混用(成功不用蓝)。

## 3. 字号体系

| 场景 | 类 |
|---|---|
| Markdown 正文 | `text-[15px] leading-relaxed` |
| 页面标题 | `text-xl font-bold` |
| 卡片标题 | `text-xs font-bold` |
| 正文操作/按钮 | `text-xs font-semibold`(主按钮)/ `font-medium`(次级) |
| 辅助信息/时间戳 | `text-[10px]` `text-[11px]` |
| 徽标 | `text-[9px]` `text-[10px]` |

## 4. 形状与间距

- 页面容器:`max-w-3xl ~ max-w-6xl mx-auto px-4 py-6+`
- 卡片:`rounded-2xl border bg-white shadow-xs`,内边距 `p-3 ~ p-5`
- 按钮/输入:`rounded-xl`;小元素:`rounded-lg`;徽标:`rounded`
- 卡片标题栏:`border-b border-slate-100 px-4 py-3`
- 垂直节奏:卡片间 `gap-3`(抽屉)/`gap-5`(工作台栅格);卡内行 `py-1.5`

## 5. 组件规范

### 卡片(Workbench Card)
标题栏(左标题+右 action)→ 内容 → 可选「查看全部 →」moreLink。任何中心卡遵循此三段。

### 按钮
- 主:`bg-slate-900 text-white hover:bg-slate-800 rounded-xl`
- 次:`border border-slate-200 hover:border-indigo-300 hover:text-indigo-600`
- 危险:`border-rose-200 bg-rose-50 text-rose-600`
- 禁用:`disabled:opacity-40`

### 徽标
`rounded px-1.5 py-0.5 text-[9~10px] font-medium + 语义色 border/bg`。**必须 `whitespace-nowrap`**(防竖排换行,20261017 教训)。

### 弹窗
`fixed inset-0 z-50 bg-black/40 p-4 flex items-center justify-center` + `max-w-md rounded-2xl bg-white p-6 shadow-xl`,点击遮罩关闭。

### 表单输入
label 在上(`text-[11px] font-semibold`)+ 输入框全宽;错误提示 `text-rose-500 text-[11px]`;成功提示 `border-emerald-200 bg-emerald-50`。

## 6. 对话消息规范(平台 + 白牌页一致)

| 元素 | 规范 |
|---|---|
| 用户气泡 | 右对齐 `bg-slate-900 text-white rounded-2xl`;附件:图片缩略图(max-h-48)+ 文档芯片,置于气泡上方 |
| 助手消息 | 白卡 `border-slate-200 rounded-2xl p-4`;ContentBlock 依次渲染 |
| 工具徽标 | 语义化命名(禁止"给出了填写表单"式误导);连续同类 >2 次折叠为单行 |
| 流式状态 | 正文前 reasoning 面板(violet);等待时三点 bounce |
| 错误 | `[错误]` 前缀进正文 + `text-rose` 语义;**禁止静默吞错** |
| 截断/降级提示 | blockquote(`> ⚠️ …`)置于消息末尾 |

## 7. 插件 output_block 组件约定

- **必须**用 output_block 工具下发,**严禁**正文 markdown 伪造组件(如 ```json 假卡片)
- 语义化 type:核心指标 `metric_stat`、对比 `table`、流程 `waterfall`、说明 `card`、
  大段正文**不要**包 card(避免前端只出标题)
- 表格数据:`columns`(字符串数组)+ `rows`(数组行),勿用 `headers`
- 文档数据一律**对象**,**严禁 JSON 字符串**(前端取空致组件空白,20261016 实证)
- 组件内文字遵循第 2/3 节色板与字号

## 8. 插件 markdown 正文约定

- 直接交付结论,**严禁**内心独白/元语言(「用户在询问…让我调用…」)
- 中文回复;表格用 GFM 管道语法;数学公式用 `$$…$$`/`$…$`;图表用 ```mermaid
- 严禁在正文中输出 `output_block(...)` 代码或 emoji 假装卡片
- 长回复可能被截断——章节化输出,末尾留「继续」衔接点

## 9. 白牌页(用户端)规范

- 单列居中 `max-w-3xl`,**无平台导航/无技术元素**(工具徽标折叠、状态条不展示)
- 首屏四件套:头像 + 名称 + **故事化 description** + 引导问题按钮(≤5 条,首条直击核心动作)
- 「我的」抽屉承载个人能力(文件/订阅/待办),不引入平台导航

## 10. 移动端

- 断点:`sm:640 / md:768 / lg:1024`;移动端优先保证单列可用
- 表格:容器 `overflow-x-auto` + `min-w` 内表(防挤成窄条)
- 导航:md 以下汉堡菜单;徽标/按钮 `whitespace-nowrap` 防竖排
- 触控目标 ≥44px(按钮 py-2.5 起步)

## 11. 已知欠账(演进项,新代码不得加剧)

1. 无 design tokens(CSS variables)——色板散落在类名中,改主题需全局替换
2. MarkdownRenderer 手写实现——数学/mermaid 为增量挂载,重写需保持 11 节约定
3. 少数历史页面未对齐本标准(渐进对齐,改动哪页就规范哪页)

## 12. 违例示例(20261017 扫描实录)

- 徽标竖排换行(缺 whitespace-nowrap)→ 已修
- 手机导航按钮溢出(插件连接未收敛)→ 已修
- 组件空白(data 传 JSON 字符串)→ 已修(服务端归一化)
