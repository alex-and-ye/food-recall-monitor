/**
 * App shell that composes the sidebar, header, and main content area, with
 * map-page layout adjustments and responsive sidebar open state.
 */

"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import Header from "@/components/Header";
import Sidebar from "@/components/Sidebar";

/** Minimum viewport width (px) treated as desktop for default-open sidebar. */
const DESKTOP_BREAKPOINT = 768;

/**
 * Wraps page children with dashboard chrome and responsive sidebar behavior.
 *
 * @param props.children - Route page content.
 * @returns Shell layout element.
 */
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

  const isMapPage = pathname === "/globe";

  return (
    <div className={`${isMapPage ? "h-screen overflow-hidden bg-slate-950" : "min-h-screen bg-slate-50"}`}>
      <Sidebar
        isOpen={isOpen}
        onToggle={() => setIsOpen((prev) => !prev)}
        onClose={() => setIsOpen(false)}
      />
      <div
        className={`flex flex-col transition-[margin] duration-300 ease-in-out ${
          isMapPage ? "h-screen overflow-hidden" : "min-h-screen"
        } ${isOpen ? "md:ml-64" : "md:ml-0"}`}
      >
        <Header />
        <main
          className={
            isMapPage
              ? "relative flex min-h-0 w-full flex-1 flex-col overflow-hidden bg-slate-950 p-0"
              : "mx-auto w-full max-w-7xl flex-1 p-4 sm:p-6 lg:p-8"
          }
        >
          {children}
        </main>
      </div>
    </div>
  );
}
