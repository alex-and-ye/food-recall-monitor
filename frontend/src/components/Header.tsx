"use client";

import PipelineRefreshButton from "@/components/PipelineRefreshButton";

export default function Header() {
  return (
    <header className="border-b border-emerald-700 bg-emerald-600 px-4 py-6 shadow-sm sm:px-6 sm:py-8">
      <div className="mx-auto flex max-w-7xl flex-col items-center gap-4 sm:relative sm:block">
        <h1 className="text-center text-3xl font-bold tracking-tight text-white">
          Food Recall Monitor
        </h1>
        <div className="w-full sm:absolute sm:top-1/2 sm:right-0 sm:w-auto sm:-translate-y-1/2">
          <PipelineRefreshButton />
        </div>
      </div>
    </header>
  );
}
