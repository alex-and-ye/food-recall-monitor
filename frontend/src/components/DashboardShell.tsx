"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import Header from "@/components/Header";
import Sidebar from "@/components/Sidebar";

const DESKTOP_BREAKPOINT = 768;

export default function DashboardShell({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const pathname = usePathname();
  const [isOpen, setIsOpen] = useState(false);

  useEffect(() => {
    if (window.innerWidth >= DESKTOP_BREAKPOINT) {
      setIsOpen(true);
    }
  }, []);

  useEffect(() => {
    if (window.innerWidth < DESKTOP_BREAKPOINT) {
      setIsOpen(false);
    }
  }, [pathname]);

  return (
    <div className="min-h-screen bg-slate-50">
      <Sidebar
        isOpen={isOpen}
        onToggle={() => setIsOpen((prev) => !prev)}
        onClose={() => setIsOpen(false)}
      />
      <div
        className={`flex min-h-screen flex-col transition-[margin] duration-300 ease-in-out ${
          isOpen ? "md:ml-64" : "md:ml-0"
        }`}
      >
        <Header />
        <main className="mx-auto w-full max-w-7xl flex-1 p-4 sm:p-6 lg:p-8">
          {children}
        </main>
      </div>
    </div>
  );
}
