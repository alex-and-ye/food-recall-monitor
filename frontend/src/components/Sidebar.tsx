/**
 * Collapsible sidebar navigation with sectioned links and an unacknowledged
 * pipeline-warning badge.
 */

"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { getWarningsSummary } from "@/services/api/client";

/**
 * Renders a hamburger menu icon used for open/close controls.
 *
 * @returns SVG icon element.
 */
function HamburgerIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className="h-6 w-6"
      aria-hidden="true"
    >
      <path d="M4 6h16M4 12h16M4 18h16" />
    </svg>
  );
}

/**
 * Renders the official recalls / feed navigation icon.
 *
 * @returns SVG icon element.
 */
function FeedIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className="h-5 w-5 shrink-0"
      aria-hidden="true"
    >
      <path d="M4 11a9 9 0 0 1 9 9M4 4a16 16 0 0 1 16 16" />
      <circle cx="5" cy="19" r="1" />
    </svg>
  );
}

/**
 * Renders the statistics navigation icon.
 *
 * @returns SVG icon element.
 */
function StatsIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className="h-5 w-5 shrink-0"
      aria-hidden="true"
    >
      <path d="M18 20V10M12 20V4M6 20v-6" />
    </svg>
  );
}

/**
 * Renders the globe map navigation icon.
 *
 * @returns SVG icon element.
 */
function GlobeIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className="h-5 w-5 shrink-0"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="10" />
      <path d="M2 12h20" />
      <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
    </svg>
  );
}

/**
 * Renders the pipeline warnings navigation icon.
 *
 * @returns SVG icon element.
 */
function WarningIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className="h-5 w-5 shrink-0"
      aria-hidden="true"
    >
      <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
      <path d="M12 9v4" />
      <path d="M12 17h.01" />
    </svg>
  );
}

/**
 * Renders the early-warnings / incidents navigation icon.
 *
 * @returns SVG icon element.
 */
function IncidentIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className="h-5 w-5 shrink-0"
      aria-hidden="true"
    >
      <path d="M12 3v3M12 18v3M3 12h3M18 12h3" />
      <circle cx="12" cy="12" r="4" />
      <path d="m5.64 5.64 2.12 2.12M16.24 16.24l2.12 2.12M18.36 5.64l-2.12 2.12M7.76 16.24l-2.12 2.12" />
    </svg>
  );
}

/** Grouped navigation sections and links shown in the sidebar. */
const NAV_SECTIONS = [
  {
    label: "Official recalls",
    links: [
      {
        href: "/",
        label: "Official Recalls",
        icon: FeedIcon,
        activePrefixes: ["/alerts"],
      },
      {
        href: "/stats",
        label: "Statistics",
        icon: StatsIcon,
        activePrefixes: [],
      },
      {
        href: "/globe",
        label: "Globe Map",
        icon: GlobeIcon,
        activePrefixes: [],
      },
    ],
  },
  {
    label: "Discovery",
    links: [
      {
        href: "/early-warnings",
        label: "Early Warnings",
        icon: IncidentIcon,
        activePrefixes: ["/incidents"],
      },
    ],
  },
  {
    label: "Operations",
    links: [
      {
        href: "/warnings",
        label: "Pipeline Issues",
        icon: WarningIcon,
        activePrefixes: [],
      },
    ],
  },
] as const;

/** Props for the sidebar component. */
interface SidebarProps {
  isOpen: boolean;
  onToggle: () => void;
  onClose: () => void;
}

/**
 * Renders the dashboard sidebar, floating open button, and mobile overlay.
 *
 * @param props.isOpen - Whether the drawer is visible.
 * @param props.onToggle - Toggles open/closed state.
 * @param props.onClose - Closes the drawer (e.g. mobile overlay click).
 * @returns Sidebar chrome and navigation links.
 */
export default function Sidebar({ isOpen, onToggle, onClose }: SidebarProps) {
  const pathname = usePathname();
  const [unacknowledgedCount, setUnacknowledgedCount] = useState(0);

  useEffect(() => {
    let cancelled = false;

    getWarningsSummary()
      .then((summary) => {
        if (!cancelled) {
          setUnacknowledgedCount(summary.unacknowledged_count);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setUnacknowledgedCount(0);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [pathname]);

  return (
    <>
      <button
        type="button"
        onClick={onToggle}
        className={`fixed top-4 left-4 z-50 rounded-lg bg-slate-800 p-2 text-white shadow-lg transition-opacity ${
          isOpen ? "pointer-events-none opacity-0" : "opacity-100"
        }`}
        aria-label="Open navigation menu"
      >
        <HamburgerIcon />
      </button>

      {isOpen && (
        <button
          type="button"
          className="fixed inset-0 z-40 bg-black/40 md:hidden"
          onClick={onClose}
          aria-label="Close navigation menu"
        />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-50 flex w-64 flex-col overflow-y-auto bg-slate-800 text-slate-100 shadow-xl transition-transform duration-300 ease-in-out ${
          isOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex items-center justify-between border-b border-slate-700 px-4 py-4">
          <span className="text-sm font-semibold tracking-wide text-slate-300 uppercase">
            Navigation
          </span>
          <button
            type="button"
            onClick={onToggle}
            className="rounded-lg p-1.5 text-slate-300 hover:bg-slate-700 hover:text-white"
            aria-label="Close navigation menu"
          >
            <HamburgerIcon />
          </button>
        </div>

        <nav className="flex flex-1 flex-col gap-5 p-3">
          {NAV_SECTIONS.map((section) => (
            <div key={section.label}>
              <p className="mb-1.5 px-3 text-xs font-semibold tracking-wider text-slate-500 uppercase">
                {section.label}
              </p>
              <div className="space-y-1">
                {section.links.map(
                  ({ href, label, icon: Icon, activePrefixes }) => {
                    const isActive =
                      href === "/"
                        ? pathname === "/" ||
                          activePrefixes.some((prefix) =>
                            pathname.startsWith(prefix),
                          )
                        : pathname.startsWith(href) ||
                          activePrefixes.some((prefix) =>
                            pathname.startsWith(prefix),
                          );

                    return (
                      <Link
                        key={href}
                        href={href}
                        className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
                          isActive
                            ? "bg-emerald-600 text-white"
                            : "text-slate-300 hover:bg-slate-700 hover:text-white"
                        }`}
                      >
                        <Icon />
                        <span className="flex-1">{label}</span>
                        {href === "/warnings" &&
                        unacknowledgedCount > 0 ? (
                          <span
                            className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
                              isActive
                                ? "bg-white/20 text-white"
                                : "bg-amber-500 text-slate-900"
                            }`}
                          >
                            {unacknowledgedCount > 99
                              ? "99+"
                              : unacknowledgedCount}
                          </span>
                        ) : null}
                      </Link>
                    );
                  },
                )}
              </div>
            </div>
          ))}
        </nav>
      </aside>
    </>
  );
}
