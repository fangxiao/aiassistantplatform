"use client";

import React, { useEffect, useState } from "react";
import { apiGet } from "../../lib/api/client";
import { Card } from "./WorkbenchView";

/** 学习进度卡(M36):今日/本周/streak/各科——学生的正反馈面板。 */

interface StudyStats {
  today_count: number;
  today_accuracy: number | null;
  week_count: number;
  week_subjects: Record<string, number>;
  total_count: number;
  streak_days: number;
}

const SUBJECT_LABEL: Record<string, string> = {
  chinese: "语文",
  english: "英语",
  math: "数学",
  other: "综合",
};

export function StudyProgressCard() {
  const [stats, setStats] = useState<StudyStats | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = () =>
      apiGet<StudyStats>("/study/stats")
        .then(setStats)
        .catch(() => setStats(null));
    void load();
    const timer = setInterval(load, 60_000);
    const onChanged = () => void load();
    window.addEventListener("ap:tasks-changed", onChanged);
    return () => {
      clearInterval(timer);
      window.removeEventListener("ap:tasks-changed", onChanged);
    };
  }, []);

  return (
    <Card title="📚 学习进度">
      {error && <p className="text-xs text-rose-500">{error}</p>}
      {stats && (
        <div className="space-y-3">
          {/* streak + 今日 */}
          <div className="flex items-center justify-between">
            <div className="flex items-baseline gap-2">
              <span className="text-2xl font-black text-orange-500">{stats.streak_days}</span>
              <span className="text-xs text-slate-500">天连续 🔥</span>
            </div>
            <div className="text-right">
              <span className="text-lg font-bold text-slate-800">{stats.today_count}</span>
              <span className="ml-1 text-[10px] text-slate-400">今日</span>
              {stats.today_accuracy !== null && (
                <span className="ml-2 text-xs font-medium text-emerald-600">{stats.today_accuracy}%</span>
              )}
            </div>
          </div>

          {/* 各科横条 */}
          {Object.keys(stats.week_subjects).length > 0 && (
            <div className="space-y-1.5">
              {Object.entries(stats.week_subjects)
                .sort((a, b) => b[1] - a[1])
                .map(([subj, count]) => {
                  const max = Math.max(...Object.values(stats.week_subjects));
                  const pct = (count / max) * 100;
                  return (
                    <div key={subj} className="flex items-center gap-2">
                      <span className="w-8 text-[10px] text-slate-500">{SUBJECT_LABEL[subj] || subj}</span>
                      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-100">
                        <div
                          className="h-full rounded-full bg-indigo-400 transition-all"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                      <span className="w-6 text-right text-[10px] font-medium text-slate-600">{count}</span>
                    </div>
                  );
                })}
            </div>
          )}

          {/* 底部累计 */}
          <div className="flex justify-between border-t border-slate-100 pt-2 text-[10px] text-slate-400">
            <span>本周 {stats.week_count} 项</span>
            <span>累计 {stats.total_count} 项</span>
          </div>
        </div>
      )}
      {stats === null && !error && <p className="py-2 text-center text-xs text-slate-400">加载中…</p>}
    </Card>
  );
}
