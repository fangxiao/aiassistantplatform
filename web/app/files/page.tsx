"use client";

/** 我的文件专属页(20261015):全部上传附件 + 一键转存知识库 */

import React from "react";
import { Navbar } from "../../components/layout/Navbar";
import { MyFilesCard } from "../../components/workbench/MyFilesCard";

export default function FilesPage() {
  return (
    <div className="flex min-h-screen flex-col bg-slate-50">
      <Navbar />
      <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-6 sm:px-6">
        <MyFilesCard full />
      </main>
    </div>
  );
}
