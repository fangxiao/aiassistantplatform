// 极简 markdown 渲染器(无第三方依赖;输出转义 HTML 防 XSS)
// 支持:标题 / 代码块 / 行内代码 / 加粗 / 斜体 / 列表 / 段落 / 链接

"use client";

import type { ReactNode } from "react";
import type { ContentBlock } from "../../lib/types";
import { BlockRenderer } from "./BlockRenderer";

type InteractFn = (action: string, value: any, args?: Record<string, any>) => void;

/**
 * 伪调用兜底(规范 4.1 确定性转换):弱模型常把 input.form({...}) 当普通文本
 * 输出而非发起真实 output_block 调用,用户看到的是无法交互的死文本。此处识别
 * 该模式并确定性转换为真实表单控件(action=input.form,提交后经 interact
 * 通道以【表单提交】回填会话,agent 据此续跑)。
 */
export function parsePseudoForm(src: string): ContentBlock | null {
  if (!/^\s*input\.form\s*\(/.test(src)) return null;
  const fieldRe = /["'“”]?([^"'“”:(){}]+?)["'“”]?\s*:\s*input\.(\w+)\s*\(([^)]*)\)/g;
  const fields: Record<string, unknown>[] = [];
  let m: RegExpExecArray | null;
  while ((m = fieldRe.exec(src))) {
    const label = m[1].trim();
    if (!label || label === "fields") continue;
    const field: Record<string, unknown> = { key: label, label, widget: m[2] };
    const opts = Array.from(m[3].matchAll(/["']([^"']+)["']/g), (x) => x[1]);
    if (opts.length) field.options = opts;
    fields.push(field);
  }
  if (!fields.length) return null;
  return {
    type: "input.form",
    data: {
      title: "请填写以下信息",
      description: "填写后助手将立即继续执行",
      fields,
      submit_text: "提交并继续",
      action: "input.form",
    },
  };
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// 行内格式: `code`、**bold**、*italic*、[text](url)
function inline(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const re = /(`[^`]+`)|(\*\*[^*]+\*\*)|(\*[^*]+\*)|(\[[^\]]+\]\([^)]+\))/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let key = 0;
  while ((m = re.exec(text))) {
    if (m.index > last) nodes.push(text.slice(last, m.index));
    const [full] = m;
    if (full.startsWith("`")) {
      nodes.push(
        <code key={key++} className="rounded bg-slate-100 px-1 text-sm">
          {escapeHtml(full.slice(1, -1))}
        </code>,
      );
    } else if (full.startsWith("**")) {
      nodes.push(<strong key={key++}>{full.slice(2, -2)}</strong>);
    } else if (full.startsWith("*")) {
      nodes.push(<em key={key++}>{full.slice(1, -1)}</em>);
    } else {
      const mm = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(full);
      if (mm) {
        nodes.push(
          <a key={key++} href={mm[2]} className="text-blue-600 underline" target="_blank" rel="noreferrer">
            {mm[1]}
          </a>,
        );
      } else {
        nodes.push(full);
      }
    }
    last = re.lastIndex;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

export default function MarkdownRenderer({
  block,
  onInteract,
}: {
  block: ContentBlock;
  onInteract?: InteractFn;
}) {
  const text = String(block.data?.text ?? "");

  // 1. 如果整段文本为完整 HTML 根结构(如微信公众号排版 <section style="..."> 或 <!DOCTYPE)
  if (
    /^\s*<(?:section|article|div|html|!DOCTYPE)\b/i.test(text.trim()) &&
    /(?:<\/(?:section|article|div|html)>|\/>)\s*$/i.test(text.trim())
  ) {
    return (
      <div className="my-2 overflow-x-auto rounded-xl border border-slate-200/80 bg-white p-2 shadow-xs">
        <div
          className="wechat-article-preview"
          dangerouslySetInnerHTML={{ __html: text.trim() }}
        />
      </div>
    );
  }

  const lines = text.split("\n");
  const out: ReactNode[] = [];
  let key = 0;

  let i = 0;
  while (i < lines.length) {
    const line = lines[i];

    // GFM 表格:| a | b | + |---|---| 分隔行(打磨:模型输出表格此前按纯文本显示)
    if (/^\s*\|.*\|\s*$/.test(line) && i + 1 < lines.length && /^\s*\|[\s:|-]+\|\s*$/.test(lines[i + 1])) {
      const parseRow = (row: string): string[] =>
        row.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());
      const header = parseRow(line);
      i += 2; // 跳过表头与分隔行
      const bodyRows: string[][] = [];
      while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) {
        bodyRows.push(parseRow(lines[i]));
        i++;
      }
      out.push(
        <div key={key++} className="my-2 overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="bg-slate-50">
                {header.map((h, hi) => (
                  <th key={hi} className="border border-slate-200 px-3 py-1.5 text-left font-semibold text-slate-700">
                    {inline(h)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {bodyRows.map((r, ri) => (
                <tr key={ri} className="even:bg-slate-50/50">
                  {header.map((_, ci) => (
                    <td key={ci} className="border border-slate-200 px-3 py-1.5 text-slate-600">
                      {inline(r[ci] ?? "")}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      continue;
    }

    // HTML 块 (如微信排版组件 <section style="...">, <div>, <table>, <!DOCTYPE)
    if (/^\s*<(?:section|div|article|table|header|footer|main|aside|nav|blockquote|!DOCTYPE|html)\b/i.test(line.trim())) {
      const htmlBuf: string[] = [line];
      i++;
      while (
        i < lines.length &&
        !/^\s*(?:#{1,3}\s|```|[-*]\s|\d+\.\s)/.test(lines[i])
      ) {
        htmlBuf.push(lines[i]);
        if (/<\/(?:section|div|article|table|html)>\s*$/i.test(lines[i].trim())) {
          i++;
          break;
        }
        i++;
      }
      const fullHtml = htmlBuf.join("\n");
      out.push(
        <div
          key={key++}
          className="my-3 overflow-x-auto rounded-xl border border-slate-200/80 bg-white p-2 shadow-xs"
          dangerouslySetInnerHTML={{ __html: fullHtml }}
        />
      );
      continue;
    }

    // 代码块
    if (/^```/.test(line.trim())) {
      const buf: string[] = [];
      i++;
      while (i < lines.length && !/^```/.test(lines[i].trim())) {
        buf.push(lines[i]);
        i++;
      }
      i++; // 跳过结束 ```
      // 伪调用兜底:代码块内容是 input.form({...}) 时渲染为真实表单
      const pseudoSrc = buf.join("\n");
      if (!/^```/.test(pseudoSrc)) {
        const formBlock = parsePseudoForm(pseudoSrc);
        if (formBlock) {
          out.push(<BlockRenderer key={key++} block={formBlock} onInteract={onInteract} />);
          continue;
        }
      }
      out.push(
        <pre key={key++} className="my-2 overflow-x-auto rounded bg-slate-800 p-3 text-sm text-slate-100">
          <code>{buf.join("\n")}</code>
        </pre>,
      );
      continue;
    }
    // 伪调用兜底(裸文本形态,无代码围栏):input.form({...}) 直接写在正文里
    if (/^\s*input\.form\s*\(/.test(line)) {
      const formBuf: string[] = [line];
      while (
        formBuf.length < 30 &&
        !/\}\s*\)\s*;?\s*$/.test(formBuf[formBuf.length - 1] ?? "") &&
        i + 1 < lines.length
      ) {
        i++;
        formBuf.push(lines[i]);
      }
      const formBlock = parsePseudoForm(formBuf.join("\n"));
      if (formBlock) {
        out.push(<BlockRenderer key={key++} block={formBlock} onInteract={onInteract} />);
        i++;
        continue;
      }
      // 解析失败:按代码块原样展示,不吞内容
      out.push(
        <pre key={key++} className="my-2 overflow-x-auto rounded bg-slate-800 p-3 text-sm text-slate-100">
          <code>{formBuf.join("\n")}</code>
        </pre>,
      );
      i++;
      continue;
    }
    // 标题
    const h = /^(#{1,3})\s+(.*)$/.exec(line);
    if (h) {
      const level = h[1].length;
      const Tag = (["h1", "h2", "h3"] as const)[level - 1];
      out.push(
        <Tag key={key++} className="my-2 font-bold">
          {inline(h[2])}
        </Tag>,
      );
      i++;
      continue;
    }
    // 列表
    const li = /^\s*[-*]\s+(.*)$/.exec(line) || /^\s*\d+\.\s+(.*)$/.exec(line);
    if (li) {
      const items: string[] = [li[1]];
      i++;
      while (i < lines.length && (/^\s*[-*]\s+/.test(lines[i]) || /^\s*\d+\.\s+/.test(lines[i]))) {
        items.push((/^\s*[-*]\s+(.*)$/.exec(lines[i]) ?? /^\s*\d+\.\s+(.*)$/.exec(lines[i]))![1]);
        i++;
      }
      out.push(
        <ul key={key++} className="my-2 list-disc pl-5">
          {items.map((it, j) => (
            <li key={j}>{inline(it)}</li>
          ))}
        </ul>,
      );
      continue;
    }
    // 空行或段落
    if (line.trim() === "") {
      i++;
      continue;
    }
    out.push(
      <p key={key++} className="my-1">
        {inline(line)}
      </p>,
    );
    i++;
  }

  return <div className="text-[15px] leading-relaxed">{out}</div>;
}
