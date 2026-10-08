"use client";

import React, { useEffect, useState } from "react";
import { apiGet, apiPost } from "../../lib/api/client";

/** 添加自定义模型供应商(M29/需求 018,参考 WorkBuddy/Trae):
 *  预设选择 → base_url 预填 → API Key → 保存即验证并拉取模型列表勾选;
 *  验证失败可保存(unverified,内网/非标上游),模型可手填。 */

interface Props {
  onClose: () => void;
  onCreated?: () => void;
}

interface Presets {
  [key: string]: { label: string; base_url: string };
}

type Step = "form" | "pick";

export function ProviderModal({ onClose, onCreated }: Props) {
  const [presets, setPresets] = useState<Presets>({});
  const [step, setStep] = useState<Step>("form");
  const [preset, setPreset] = useState("deepseek");
  const [name, setName] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 验证结果
  const [verified, setVerified] = useState(false);
  const [probeMsg, setProbeMsg] = useState("");
  const [found, setFound] = useState<string[]>([]);
  const [picked, setPicked] = useState<Record<string, boolean>>({});
  const [manualModel, setManualModel] = useState("");

  useEffect(() => {
    apiGet<{ providers: unknown[]; presets: Presets }>("/llm/providers")
      .then((d) => setPresets(d.presets || {}))
      .catch(() => setPresets({}));
  }, []);

  useEffect(() => {
    setBaseUrl(presets[preset]?.base_url ?? "");
    setName(presets[preset]?.label ?? "");
  }, [preset, presets]);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const r = await apiPost<{
        id: string;
        status: string;
        verified: boolean;
        models_found: string[];
        message: string;
      }>("/llm/providers", {
        name: name.trim(),
        preset,
        base_url: baseUrl.trim(),
        api_key: apiKey.trim(),
        models: [],
      });
      if (r.verified && r.models_found.length > 0) {
        setVerified(true);
        setFound(r.models_found);
        setPicked({});
        setStep("pick");
        setProviderId(r.id);
      } else {
        // 验证失败或无列表:直接完成(可稍后在开发者中心手填/重试)
        onCreated?.();
        onClose();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "添加失败");
    } finally {
      setBusy(false);
    }
  };

  const [providerId, setProviderId] = useState<string | null>(null);

  const saveModels = async () => {
    if (!providerId) return onClose();
    const models = [...Object.keys(picked).filter((k) => picked[k]), ...manualModel.split(",")];
    setBusy(true);
    try {
      await apiPost(`/llm/providers/${providerId}/models`, { models });
      onCreated?.();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4 backdrop-blur-xs">
      <div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl space-y-4">
        <div className="flex items-center justify-between border-b border-slate-100 pb-3">
          <h3 className="text-sm font-bold text-slate-900">
            {step === "form" ? "🔌 添加自定义模型供应商" : "✅ 选择要启用的模型"}
          </h3>
          <button type="button" onClick={onClose} className="text-slate-400 hover:text-slate-600">✕</button>
        </div>

        {step === "form" ? (
          <div className="space-y-3 text-xs">
            <div>
              <label className="mb-1 block text-slate-600">供应商</label>
              <div className="grid grid-cols-3 gap-1.5">
                {Object.entries(presets).map(([key, p]) => (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setPreset(key)}
                    className={`rounded-md border px-2 py-1.5 font-medium transition ${
                      preset === key
                        ? "border-indigo-500 bg-indigo-50 text-indigo-700"
                        : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                    }`}
                  >
                    {p.label}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <label className="mb-1 block text-slate-600">显示名称</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full rounded-md border border-slate-300 px-3 py-1.5 focus:border-indigo-500 focus:outline-hidden"
              />
            </div>
            <div>
              <label className="mb-1 block text-slate-600">接口地址(Base URL,OpenAI 兼容)</label>
              <input
                type="text"
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                placeholder="https://api.example.com/v1"
                className="w-full rounded-md border border-slate-300 px-3 py-1.5 font-mono focus:border-indigo-500 focus:outline-hidden"
              />
            </div>
            <div>
              <label className="mb-1 block text-slate-600">API Key(加密存储,仅本人可用)</label>
              <input
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="sk-…"
                className="w-full rounded-md border border-slate-300 px-3 py-1.5 font-mono focus:border-indigo-500 focus:outline-hidden"
              />
            </div>
            <p className="rounded-md bg-slate-50 px-3 py-2 text-[11px] text-slate-500">
              保存时平台会验证连通性并拉取你的可用模型列表;验证失败也可保存(稍后重试或手填模型)。
            </p>
            {error && <p className="text-[11px] text-rose-500">{error}</p>}
            <div className="flex justify-end gap-2 pt-1">
              <button type="button" onClick={onClose} className="rounded-md px-3 py-1.5 text-slate-600 hover:bg-slate-100">取消</button>
              <button
                type="button"
                disabled={busy || !baseUrl.trim() || !apiKey.trim()}
                onClick={() => void submit()}
                className="rounded-md bg-indigo-600 px-4 py-1.5 font-semibold text-white hover:bg-indigo-500 disabled:opacity-50"
              >
                {busy ? "验证中…" : "验证并添加"}
              </button>
            </div>
          </div>
        ) : (
          <div className="space-y-3 text-xs">
            <p className="text-[11px] text-emerald-600">✅ 连通成功,发现 {found.length} 个模型,勾选要在平台使用的:</p>
            <div className="max-h-64 space-y-1 overflow-y-auto rounded-lg border border-slate-100 p-2">
              {found.map((m) => (
                <label key={m} className="flex cursor-pointer items-center gap-2 rounded px-2 py-1 hover:bg-slate-50">
                  <input
                    type="checkbox"
                    checked={!!picked[m]}
                    onChange={(e) => setPicked({ ...picked, [m]: e.target.checked })}
                    className="h-3.5 w-3.5"
                  />
                  <span className="font-mono text-[11px] text-slate-700">{m}</span>
                </label>
              ))}
            </div>
            <div>
              <label className="mb-1 block text-slate-600">手填模型(逗号分隔,可选——列表缺失时)</label>
              <input
                type="text"
                value={manualModel}
                onChange={(e) => setManualModel(e.target.value)}
                placeholder="my-model-a, my-model-b"
                className="w-full rounded-md border border-slate-300 px-3 py-1.5 font-mono"
              />
            </div>
            {error && <p className="text-[11px] text-rose-500">{error}</p>}
            <div className="flex justify-end gap-2 pt-1">
              <button type="button" onClick={() => setStep("form")} className="rounded-md px-3 py-1.5 text-slate-600 hover:bg-slate-100">上一步</button>
              <button
                type="button"
                disabled={busy || Object.values(picked).every((v) => !v)}
                onClick={() => void saveModels()}
                className="rounded-md bg-indigo-600 px-4 py-1.5 font-semibold text-white hover:bg-indigo-500 disabled:opacity-50"
              >
                {busy ? "保存中…" : "完成"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
