import { createContext } from "react";

/**
 * 渲染嵌套深度上下文:容器控件(card / collapsible / input.form)内部 depth+1。
 * 字段控件据此切换两种行为:
 * - 独立态(depth=0):自带提交按钮,提交即触发 interact 动作;
 * - 嵌套态(depth>0):隐藏自带按钮,值变化实时上报给容器表单,由容器统一提交。
 */
export const NestingContext = createContext<number>(0);
