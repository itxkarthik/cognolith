"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/lib/hooks/useAuth";
import { motion } from "motion/react";
import {
  LayoutDashboard,
  Database,
  FileText,
  MessageSquare,
  BarChart3,
  Settings,
  HelpCircle,
  Terminal,
  Plus,
} from "lucide-react";

const iconMap: Record<string, React.ReactNode> = {
  dashboard: <LayoutDashboard className="w-4 h-4" />,
  database: <Database className="w-4 h-4" />,
  description: <FileText className="w-4 h-4" />,
  smart_toy: <MessageSquare className="w-4 h-4" />,
  monitoring: <BarChart3 className="w-4 h-4" />,
  settings: <Settings className="w-4 h-4" />,
  help: <HelpCircle className="w-4 h-4" />,
};

const navItems = [
  { href: "/dashboard", label: "Dashboard", icon: "dashboard" },
  {
    href: "/dashboard/knowledge-graph",
    label: "Knowledge Base",
    icon: "database",
  },
  { href: "/dashboard/documents", label: "Documents", icon: "description" },
  { href: "/dashboard/notes", label: "Notes", icon: "description" },
  { href: "/dashboard/chat", label: "Chat Assistant", icon: "smart_toy" },
  { href: "/dashboard/search", label: "Analytics", icon: "monitoring" },
];

const secondaryNavItems = [
  { href: "/dashboard/settings", label: "Settings", icon: "settings" },
  { href: "#support", label: "Support", icon: "help" },
];

interface NavItemProps {
  item: { href: string; label: string; icon: string };
  isActive: boolean;
}

function NavItem({ item, isActive }: NavItemProps) {
  return (
    <motion.div whileHover={{ x: 4 }} transition={{ duration: 0.18 }}>
      <Link
      href={item.href}
      className={`group flex items-center gap-3 rounded-xl px-4 py-3 text-sm tracking-tight transition-all duration-300 ${
        isActive
          ? "border border-cyan-400/40 bg-cyan-500/15 text-cyan-200 shadow-[0_0_20px_rgba(0,255,255,0.2)]"
          : "border border-transparent text-cyan-100/65 hover:border-cyan-500/30 hover:bg-cyan-500/10 hover:text-cyan-100"
      }`}
    >
      <div className="flex-shrink-0">
        {iconMap[item.icon] || iconMap.dashboard}
      </div>
      <span className="text-xs font-semibold uppercase tracking-[0.16em]">{item.label}</span>
      </Link>
    </motion.div>
  );
}

export function Sidebar() {
  const pathname = usePathname();
  const { user } = useAuth();

  return (
    <aside className="fixed left-0 top-0 z-40 hidden h-full w-72 flex-col border-r border-cyan-500/25 bg-[#060916]/90 font-['Space_Grotesk'] text-sm tracking-tight backdrop-blur-xl lg:flex">
      <div className="p-6">
        <div className="flex items-center gap-3 mb-8">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-cyan-400/40 bg-cyan-500/15 shadow-[0_0_20px_rgba(0,255,255,0.25)]">
            <Terminal className="h-5 w-5 text-cyan-200" />
          </div>
          <div>
            <h1 className="text-sm font-extrabold uppercase tracking-[0.12em] text-cyan-100">
              Personal Knowledge AI
            </h1>
            <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-cyan-300/65">
              Neon Ops Console
            </p>
          </div>
        </div>

        <button className="mb-8 flex w-full items-center justify-center gap-2 rounded-xl border border-cyan-400/35 bg-gradient-to-r from-cyan-500/20 via-fuchsia-500/15 to-cyan-500/20 px-4 py-3 font-bold text-cyan-100 transition-all hover:shadow-[0_0_30px_rgba(0,255,255,0.25)]">
          <Plus className="w-4 h-4" />
          <span className="text-xs font-bold uppercase tracking-[0.16em]">New Entry</span>
        </button>

        <nav className="space-y-2">
          {navItems.map((item) => {
            const isActive =
              pathname === item.href ||
              (item.href !== "/dashboard" && pathname.startsWith(item.href));
            return <NavItem key={item.href} item={item} isActive={isActive} />;
          })}
        </nav>
      </div>

      <div className="mt-auto space-y-2 p-6">
        <nav className="space-y-2">
          {secondaryNavItems.map((item) => {
            const isActive = pathname === item.href;
            return <NavItem key={item.href} item={item} isActive={isActive} />;
          })}
        </nav>

        <div className="flex items-center gap-3 border-t border-cyan-500/20 pt-6">
          <div className="flex h-8 w-8 items-center justify-center overflow-hidden rounded-full border border-cyan-500/40 bg-cyan-500/10 text-xs font-bold text-cyan-100/80">
            {user?.full_name?.[0]?.toUpperCase() ?? "U"}
          </div>
          <div className="overflow-hidden">
            <p className="truncate text-xs font-bold text-cyan-50">
              {user?.full_name ?? "Operator_01"}
            </p>
            <p className="truncate font-mono text-[10px] uppercase tracking-[0.14em] text-cyan-300/65">
              Status: Active
            </p>
          </div>
        </div>
      </div>
    </aside>
  );
}
