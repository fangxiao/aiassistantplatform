"use client";

/** 定时任务专属页(20261015 汇总化):工作台只放最近 5 条,这里看全部 */

import React from "react";
import { Navbar } from "../../components/layout/Navbar";
import { SchedulerCard } from "../../components/workbench/SchedulerCard";

export default function SchedulerPage() {
  return (
    <div className="flex min-h-screen flex-col bg-slate-50">
      <Navbar />
      <main className="mx-auto w-full max-w-4xl flex-1 px-4 py-6 sm:px-6">
        <SchedulerCard onContinue={(sid) => { window.location.href = `/?sessionId=${sid}`; }} full />
      </main>
    </div>
  );
}
