"use client";

import React, { useContext, useState } from "react";
import { ContentBlock } from "../../../lib/types";
import { BlockRenderer } from "../BlockRenderer";
import { NestingContext } from "../blockContext";

interface ControlProps {
  block: ContentBlock;
  onInteract?: (action: string, value: any, args?: Record<string, any>) => void;
}

/**
 * 字段控件的嵌套态支持(表单容器内复用同一套控件):
 * - nested(容器内):隐藏自带提交按钮,值变化实时上报容器(onChange),由容器统一提交;
 * - 独立态:保持原行为——自带按钮,点击才触发 interact 动作。
 * 上报键优先取 data.action(表单容器 normalize 后= 字段唯一 id),保证各字段不串值。
 */
function useFieldReport(block: ContentBlock, onInteract?: ControlProps["onInteract"]) {
  const depth = useContext(NestingContext);
  const nested = depth > 0;
  const key = String(block.data?.action ?? block.data?.id ?? block.data?.label ?? "field");
  const report = (value: unknown) => {
    if (nested) onInteract?.(key, { value });
  };
  return { nested, key, report };
}

/** options 兼容:模型常给字符串数组(如 ["专业","轻松"]),统一成 {label,value} */
function normalizeOptions(options: unknown): { label: string; value: string }[] {
  return (Array.isArray(options) ? options : []).map((o) =>
    typeof o === "string" ? { label: o, value: o } : { label: String(o?.label ?? o), value: String(o?.value ?? o) },
  );
}

// 1. input.text
export function InputTextRenderer({ block, onInteract }: ControlProps) {
  const [val, setVal] = useState(String(block.data?.default ?? ""));
  const { nested, report } = useFieldReport(block, onInteract);
  const action = String(block.data?.action ?? "input.text");
  const label = block.data?.label ? String(block.data.label) : null;
  const placeholder = String(block.data?.placeholder ?? "请输入...");

  return (
    <div className="my-2 max-w-md rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
      {label && <label className="mb-1 block text-xs font-semibold text-slate-700">{label}</label>}
      <div className="flex gap-2">
        <input
          type="text"
          value={val}
          placeholder={placeholder}
          onChange={(e) => {
            setVal(e.target.value);
            report(e.target.value);
          }}
          className="flex-1 rounded border border-slate-300 px-3 py-1.5 text-xs text-slate-800 focus:border-slate-500 focus:outline-none"
        />
        {!nested && (
          <button
            type="button"
            onClick={() => onInteract?.(action, { value: val }, block.data?.args)}
            className="rounded bg-slate-800 px-3 py-1.5 text-xs font-medium text-white hover:bg-slate-700 transition"
          >
            提交
          </button>
        )}
      </div>
    </div>
  );
}

// 2. input.textarea
export function InputTextareaRenderer({ block, onInteract }: ControlProps) {
  const [val, setVal] = useState(String(block.data?.default ?? ""));
  const { nested, report } = useFieldReport(block, onInteract);
  const action = String(block.data?.action ?? "input.textarea");
  const label = block.data?.label ? String(block.data.label) : null;
  const placeholder = String(block.data?.placeholder ?? "请输入多行文本...");

  return (
    <div className="my-2 max-w-md rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
      {label && <label className="mb-1 block text-xs font-semibold text-slate-700">{label}</label>}
      <textarea
        rows={3}
        value={val}
        placeholder={placeholder}
        onChange={(e) => {
          setVal(e.target.value);
          report(e.target.value);
        }}
        className="w-full rounded border border-slate-300 p-2 text-xs text-slate-800 focus:border-slate-500 focus:outline-none"
      />
      {!nested && (
        <div className="mt-2 flex justify-end">
          <button
            type="button"
            onClick={() => onInteract?.(action, { value: val }, block.data?.args)}
            className="rounded bg-slate-800 px-3 py-1.5 text-xs font-medium text-white hover:bg-slate-700 transition"
          >
            提交
          </button>
        </div>
      )}
    </div>
  );
}

// 3. input.number
export function InputNumberRenderer({ block, onInteract }: ControlProps) {
  const [val, setVal] = useState<number>(Number(block.data?.default ?? 0));
  const { nested, report } = useFieldReport(block, onInteract);
  const action = String(block.data?.action ?? "input.number");
  const label = block.data?.label ? String(block.data.label) : null;

  return (
    <div className="my-2 max-w-xs rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
      {label && <label className="mb-1 block text-xs font-semibold text-slate-700">{label}</label>}
      <div className="flex gap-2">
        <input
          type="number"
          value={val}
          min={block.data?.min}
          max={block.data?.max}
          step={block.data?.step ?? 1}
          onChange={(e) => {
            setVal(Number(e.target.value));
            report(Number(e.target.value));
          }}
          className="flex-1 rounded border border-slate-300 px-3 py-1.5 text-xs text-slate-800 focus:border-slate-500 focus:outline-none"
        />
        {!nested && (
          <button
            type="button"
            onClick={() => onInteract?.(action, { value: val }, block.data?.args)}
            className="rounded bg-slate-800 px-3 py-1.5 text-xs font-medium text-white hover:bg-slate-700 transition"
          >
            确定
          </button>
        )}
      </div>
    </div>
  );
}

// 4. input.select
export function InputSelectRenderer({ block, onInteract }: ControlProps) {
  const options = normalizeOptions(block.data?.options);
  const [val, setVal] = useState(String(block.data?.default ?? options[0]?.value ?? ""));
  const { nested, report } = useFieldReport(block, onInteract);
  const action = String(block.data?.action ?? "input.select");
  const label = block.data?.label ? String(block.data.label) : null;

  return (
    <div className="my-2 max-w-xs rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
      {label && <label className="mb-1 block text-xs font-semibold text-slate-700">{label}</label>}
      <div className="flex gap-2">
        <select
          value={val}
          onChange={(e) => {
            setVal(e.target.value);
            report(e.target.value);
          }}
          className="flex-1 rounded border border-slate-300 px-2 py-1.5 text-xs text-slate-800 focus:border-slate-500 focus:outline-none"
        >
          {options.map((opt, i) => (
            <option key={i} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        {!nested && (
          <button
            type="button"
            onClick={() => onInteract?.(action, { value: val }, block.data?.args)}
            className="rounded bg-slate-800 px-3 py-1.5 text-xs font-medium text-white hover:bg-slate-700 transition"
          >
            选择
          </button>
        )}
      </div>
    </div>
  );
}

// 5. input.radio
export function InputRadioRenderer({ block, onInteract }: ControlProps) {
  const options = normalizeOptions(block.data?.options);
  const [val, setVal] = useState(String(block.data?.default ?? ""));
  const { nested, report } = useFieldReport(block, onInteract);
  const action = String(block.data?.action ?? "input.radio");
  const label = block.data?.label ? String(block.data.label) : null;

  return (
    <div className="my-2 max-w-sm rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
      {label && <label className="mb-2 block text-xs font-semibold text-slate-700">{label}</label>}
      <div className="space-y-1.5">
        {options.map((opt, i) => (
          <label key={i} className="flex cursor-pointer items-center gap-2 text-xs text-slate-700">
            <input
              type="radio"
              name={`radio_${block.meta?.id ?? "grp"}`}
              value={opt.value}
              checked={val === opt.value}
              onChange={(e) => {
                setVal(e.target.value);
                report(e.target.value);
              }}
              className="text-slate-800"
            />
            <span>{opt.label}</span>
          </label>
        ))}
      </div>
      {!nested && (
        <button
          type="button"
          disabled={!val}
          onClick={() => onInteract?.(action, { value: val }, block.data?.args)}
          className="mt-3 w-full rounded bg-slate-800 py-1.5 text-xs font-medium text-white hover:bg-slate-700 transition disabled:opacity-50"
        >
          确认单选
        </button>
      )}
    </div>
  );
}

// 6. input.checkbox
export function InputCheckboxRenderer({ block, onInteract }: ControlProps) {
  const options = normalizeOptions(block.data?.options);
  const [val, setVal] = useState<string[]>(block.data?.default ?? []);
  const { nested, report } = useFieldReport(block, onInteract);
  const action = String(block.data?.action ?? "input.checkbox");
  const label = block.data?.label ? String(block.data.label) : null;

  const toggle = (v: string) => {
    const next = val.includes(v) ? val.filter((x) => x !== v) : [...val, v];
    setVal(next);
    report(next);
  };

  return (
    <div className="my-2 max-w-sm rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
      {label && <label className="mb-2 block text-xs font-semibold text-slate-700">{label}</label>}
      <div className="space-y-1.5">
        {options.map((opt, i) => (
          <label key={i} className="flex cursor-pointer items-center gap-2 text-xs text-slate-700">
            <input
              type="checkbox"
              value={opt.value}
              checked={val.includes(opt.value)}
              onChange={() => toggle(opt.value)}
              className="rounded text-slate-800"
            />
            <span>{opt.label}</span>
          </label>
        ))}
      </div>
      {!nested && (
        <button
          type="button"
          onClick={() => onInteract?.(action, { value: val }, block.data?.args)}
          className="mt-3 w-full rounded bg-slate-800 py-1.5 text-xs font-medium text-white hover:bg-slate-700 transition"
        >
          确认多选
        </button>
      )}
    </div>
  );
}

// 7. input.toggle
export function InputToggleRenderer({ block, onInteract }: ControlProps) {
  const [val, setVal] = useState<boolean>(Boolean(block.data?.default ?? false));
  const { nested, report } = useFieldReport(block, onInteract);
  const action = String(block.data?.action ?? "input.toggle");
  const label = String(block.data?.label ?? "开关设置");

  const handleToggle = () => {
    const next = !val;
    setVal(next);
    // 独立态:切换即提交动作;嵌套态:仅实时上报给容器表单
    if (nested) {
      report(next);
    } else {
      onInteract?.(action, { value: next }, block.data?.args);
    }
  };

  return (
    <div className="my-2 flex max-w-xs items-center justify-between rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
      <span className="text-xs font-medium text-slate-700">{label}</span>
      <button
        type="button"
        onClick={handleToggle}
        className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full transition-colors ${
          val ? "bg-slate-800" : "bg-slate-300"
        }`}
      >
        <span
          className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
            val ? "translate-x-4" : "translate-x-0.5"
          } mt-0.5`}
        />
      </button>
    </div>
  );
}

// 8. input.date
export function InputDateRenderer({ block, onInteract }: ControlProps) {
  const [val, setVal] = useState(String(block.data?.default ?? ""));
  const { nested, report } = useFieldReport(block, onInteract);
  const action = String(block.data?.action ?? "input.date");
  const label = block.data?.label ? String(block.data.label) : null;

  return (
    <div className="my-2 max-w-xs rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
      {label && <label className="mb-1 block text-xs font-semibold text-slate-700">{label}</label>}
      <div className="flex gap-2">
        <input
          type="date"
          value={val}
          onChange={(e) => {
            setVal(e.target.value);
            report(e.target.value);
          }}
          className="flex-1 rounded border border-slate-300 px-2 py-1 text-xs text-slate-800 focus:border-slate-500 focus:outline-none"
        />
        {!nested && (
          <button
            type="button"
            onClick={() => onInteract?.(action, { value: val }, block.data?.args)}
            className="rounded bg-slate-800 px-3 py-1.5 text-xs font-medium text-white hover:bg-slate-700 transition"
          >
            确定
          </button>
        )}
      </div>
    </div>
  );
}

// 8b. input.datetime(日期+时间组合控件)
export function InputDatetimeRenderer({ block, onInteract }: ControlProps) {
  const dateVal = String(block.data?.default ?? block.data?.defaultValue ?? "").slice(0, 10);
  const [d, setD] = useState(dateVal);
  const [t, setT] = useState("");
  const { nested, report } = useFieldReport(block, onInteract);
  const action = String(block.data?.action ?? "input.datetime");
  const label = block.data?.label ? String(block.data.label) : null;
  const withSeconds = Boolean(block.data?.withSeconds);

  const combine = (nd: string, nt: string) =>
    nd && nt ? `${nd} ${nt}${withSeconds ? ":00" : ""}` : nd || nt;

  const submit = () => {
    onInteract?.(action, { value: combine(d, t) }, block.data?.args);
  };

  return (
    <div className="my-2 max-w-sm rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
      {label && <label className="mb-1 block text-xs font-semibold text-slate-700">{label}</label>}
      <div className="flex gap-2">
        <input
          type="date"
          value={d}
          onChange={(e) => {
            setD(e.target.value);
            report(combine(e.target.value, t));
          }}
          className="flex-1 rounded border border-slate-300 px-2 py-1 text-xs text-slate-800 focus:border-slate-500 focus:outline-none"
        />
        <input
          type="time"
          step={withSeconds ? 1 : 60}
          value={t}
          onChange={(e) => {
            setT(e.target.value);
            report(combine(d, e.target.value));
          }}
          className="w-28 rounded border border-slate-300 px-2 py-1 text-xs text-slate-800 focus:border-slate-500 focus:outline-none"
        />
        {!nested && (
          <button
            type="button"
            onClick={submit}
            disabled={!d && !t}
            className="rounded bg-slate-800 px-3 py-1.5 text-xs font-medium text-white hover:bg-slate-700 transition disabled:opacity-40"
          >
            确定
          </button>
        )}
      </div>
    </div>
  );
}

// 9. input.file
export function InputFileRenderer({ block, onInteract }: ControlProps) {
  const action = String(block.data?.action ?? "input.file");
  const label = String(block.data?.label ?? "选择要上传的文件");
  const [fileName, setFileName] = useState<string | null>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setFileName(file.name);
      onInteract?.(
        action,
        { files: [{ name: file.name, size: file.size, type: file.type }] },
        block.data?.args
      );
    }
  };

  return (
    <div className="my-2 max-w-sm rounded-lg border border-dashed border-slate-300 bg-white p-4 text-center shadow-sm">
      <label className="cursor-pointer block">
        <span className="text-2xl mb-1 block">📎</span>
        <span className="text-xs font-medium text-slate-700">{label}</span>
        <input type="file" onChange={handleFileChange} className="hidden" />
      </label>
      {fileName && (
        <p className="mt-2 text-[11px] text-emerald-600 font-medium">
          已选择: {fileName}
        </p>
      )}
    </div>
  );
}

// 10. input.confirm
export function InputConfirmRenderer({ block, onInteract }: ControlProps) {
  const message = String(block.data?.message ?? block.data?.text ?? "请确认是否继续此操作?");
  const action = String(block.data?.action ?? "input.confirm");
  const confirmText = String(block.data?.confirm_text ?? "确认");
  const cancelText = String(block.data?.cancel_text ?? "取消");

  return (
    <div className="my-2 max-w-sm rounded-lg border border-slate-200 bg-slate-50 p-3.5 shadow-sm">
      <p className="text-xs font-medium text-slate-800">{message}</p>
      <div className="mt-3 flex justify-end gap-2">
        <button
          type="button"
          onClick={() => onInteract?.(action, { confirmed: false }, block.data?.args)}
          className="rounded border border-slate-300 bg-white px-3 py-1 text-xs font-medium text-slate-600 hover:bg-slate-100 transition"
        >
          {cancelText}
        </button>
        <button
          type="button"
          onClick={() => onInteract?.(action, { confirmed: true }, block.data?.args)}
          className="rounded bg-slate-800 px-3 py-1 text-xs font-medium text-white hover:bg-slate-700 transition"
        >
          {confirmText}
        </button>
      </div>
    </div>
  );
}

// 11. input.form (容器型表单)

/**
 * 字段规范化:模型常输出扁平描述 {label, name, widget, options, placeholder,
 * required, default}(而非标准 {type, data} ContentBlock)——统一转成渲染器
 * 期望的结构,避免"组件降级显示"。widget 别名映射到 22 控件体系。
 */
function normalizeFormField(f: any, i: number): ContentBlock {
  if (f?.type && f?.data && String(f.type).startsWith("input.")) return f as ContentBlock;
  const rawType = f?.type && !f?.data ? f.type : null; // 裸 type(如 "date"/"text")
  const kind = String(f?.widget ?? rawType ?? f?.input ?? f?.field_type ?? "text").replace(/^input\./, "");
  const map: Record<string, string> = {
    text: "input.text", textarea: "input.textarea", number: "input.number",
    select: "input.select", radio: "input.radio", checkbox: "input.checkbox",
    date: "input.date", datetime: "input.datetime", "datetime-local": "input.datetime",
    time: "input.text", toggle: "input.toggle", file: "input.file",
  };
  const type = map[kind] ?? "input.text";
  const fieldKey = String(f?.id ?? f?.name ?? f?.key ?? `field_${i}`);
  return {
    type,
    data: {
      id: fieldKey,
      // 嵌套态字段值上报键:唯一,容器据此按字段收集(避免全部撞在 "input.text" 上)
      action: fieldKey,
      label: f?.label ?? f?.name ?? `字段${i + 1}`,
      placeholder: f?.placeholder,
      required: Boolean(f?.required),
      options: Array.isArray(f?.options) ? f.options : undefined,
      defaultValue: f?.default,
    },
  };
}

export function InputFormRenderer({ block, onInteract }: ControlProps) {
  const title = block.data?.title ? String(block.data.title) : null;
  const action = String(block.data?.action ?? "input.form");
  const rawFields: any[] = block.data?.fields ?? [];
  const fields: ContentBlock[] = rawFields.map(normalizeFormField);
  const submitLabel = String(block.data?.submit_label ?? block.data?.submit_text ?? "提交表单");

  const [formValues, setFormValues] = useState<Record<string, any>>({});

  const handleFieldInteract = (fieldAction: string, value: any) => {
    setFormValues((prev) => ({ ...prev, [fieldAction]: value }));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    // 结构化提交:fields 列表(id/label/value)——后端 interact 服务按此渲染
    // 表格回执并注入会话;缺省字段带空值,保证 agent 拿到完整字段清单
    const fields = rawFields.map((f, i) => {
      const key = String(f?.id ?? f?.name ?? f?.key ?? `field_${i}`);
      const entry = formValues[key];
      return {
        id: key,
        label: String(f?.label ?? f?.name ?? key),
        value: entry?.value ?? entry ?? "",
      };
    });
    onInteract?.(action, { fields }, block.data?.args);
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="my-3 max-w-md rounded-lg border border-slate-200 bg-white p-4 shadow-sm"
    >
      {title && <h4 className="mb-3 text-sm font-bold text-slate-800">{title}</h4>}
      <div className="space-y-3">
        {fields.map((f, i) => (
          <BlockRenderer key={i} block={f} onInteract={handleFieldInteract} />
        ))}
      </div>
      <button
        type="submit"
        className="mt-4 w-full rounded bg-slate-800 py-2 text-xs font-medium text-white hover:bg-slate-700 transition"
      >
        {submitLabel}
      </button>
    </form>
  );
}
