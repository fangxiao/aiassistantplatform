"use client";

/** 待办专属页(20261015 汇总化):工作台只放最近几条,这里看全部 */

import React from "react";
import { Navbar } from "../../components/layout/Navbar";
import { TodoCard } from "../../components/workbench/TodoCard";

export default function TodosPage() {
  return (
    <div className="flex min-h-screen flex-col bg-slate-50">
      <Navbar />
      <main className="mx-auto w-full max-w-2xl flex-1 px-4 py-6 sm:px-6">
        <TodoCard full />
      </main>
    </div>
  );
}
