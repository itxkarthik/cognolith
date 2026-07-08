"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/lib/hooks/useAuth";
import {
  LayoutDashboard,
  Database,
  FileText,
  NotebookPen,
  MessageSquare,
  Search,
  Settings,
  HelpCircle,
  Plus,
  PanelLeftClose,
  PanelLeftOpen,
} from "lucide-react";
import { Button } from "@/components/ui";
import { cn } from "@/lib/utils/cn";

const iconMap: Record<string, React.ReactNode> = {
  dashboard: <LayoutDashboard className="h-4 w-4" />,
  database: <Database className="h-4 w-4" />,
  description: <FileText className="h-4 w-4" />,
  note: <NotebookPen className="h-4 w-4" />,
  smart_toy: <MessageSquare className="h-4 w-4" />,
  search: <Search className="h-4 w-4" />,
  settings: <Settings className="h-4 w-4" />,
  help: <HelpCircle className="h-4 w-4" />,
};

const navItems = [
  { href: "/dashboard", label: "Dashboard", icon: "dashboard" },
  { href: "/dashboard/knowledge-graph", label: "Knowledge Base", icon: "database" },
  { href: "/dashboard/documents", label: "Documents", icon: "description" },
  { href: "/dashboard/notes", label: "Notes", icon: "note" },
  { href: "/dashboard/chat", label: "Chat Assistant", icon: "smart_toy" },
  { href: "/dashboard/search", label: "Search", icon: "search" },
];

const secondaryNavItems = [
  { href: "/dashboard/settings", label: "Settings", icon: "settings" },
  { href: "/dashboard/support", label: "Support", icon: "help" },
];

interface NavItemProps {
  item: { href: string; label: string; icon: string };
  isActive: boolean;
  expanded: boolean;
}

function NavItem({ item, isActive, expanded }: NavItemProps) {
  return (
    <Link
      href={item.href}
      className={cn(
        "flex h-10 items-center border text-sm transition-colors",
        expanded ? "gap-2 px-3" : "justify-center px-0",
        isActive
          ? "border-border bg-accent text-foreground"
          : "border-transparent text-muted-foreground hover:border-border hover:bg-muted"
      )}
      title={item.label}
    >
      <span className="shrink-0 text-muted-foreground">{iconMap[item.icon] || iconMap.dashboard}</span>
      {expanded ? <span className="truncate">{item.label}</span> : null}
    </Link>
  );
}

interface SidebarProps {
  expanded: boolean;
  onToggle: () => void;
}

export function Sidebar({ expanded, onToggle }: SidebarProps) {
  const pathname = usePathname();
  const { user } = useAuth();

  return (
    <aside
      className={cn(
        "fixed left-0 top-0 z-30 hidden h-full overflow-hidden border-r border-border bg-background transition-[width] duration-200 ease-out lg:flex lg:flex-col",
        expanded ? "w-64" : "w-16"
      )}
    >
      <div className={cn("border-b border-border", expanded ? "p-5" : "p-2")}>
        <div className={cn("flex items-start", expanded ? "justify-between gap-3" : "justify-center")}>
          <div className={cn("min-w-0", expanded ? "block" : "hidden")}>
            <p className="truncate text-xs text-muted-foreground">Personal knowledge workspace</p>
            <h1 className="mt-1 truncate text-base font-bold text-foreground">Cognolith</h1>
            <p className="mt-2 text-xs leading-5 text-muted-foreground">
              Notes, documents, chats, and graph relationships in one workspace.
            </p>
          </div>
          {!expanded ? <h1 className="sr-only">Cognolith</h1> : null}
          <Button
            type="button"
            variant="outline"
            size="icon-sm"
            onClick={onToggle}
            aria-label={expanded ? "Collapse sidebar" : "Expand sidebar"}
            title={expanded ? "Collapse sidebar" : "Expand sidebar"}
            className="shrink-0"
          >
            {expanded ? <PanelLeftClose className="h-4 w-4" /> : <PanelLeftOpen className="h-4 w-4" />}
          </Button>
        </div>
      </div>

      <div className={cn(expanded ? "p-4" : "p-2")}>
        <Button asChild className="mb-4 w-full justify-center overflow-hidden" variant="default">
          <Link href="/dashboard/notes?new=1" title="New note" aria-label="New note">
            <Plus className="h-4 w-4" />
            {expanded ? <span>New note</span> : null}
          </Link>
        </Button>

        <nav className="space-y-1">
          {navItems.map((item) => {
            const isActive = pathname === item.href || (item.href !== "/dashboard" && pathname.startsWith(item.href));
            return <NavItem key={item.href} item={item} isActive={isActive} expanded={expanded} />;
          })}
        </nav>
      </div>

      <div className={cn("mt-auto border-t border-border", expanded ? "p-4" : "p-2")}>
        <nav className="space-y-1">
          {secondaryNavItems.map((item) => {
            const isActive = pathname === item.href;
            return <NavItem key={item.href} item={item} isActive={isActive} expanded={expanded} />;
          })}
        </nav>

        {expanded ? (
          <div className="mt-4 border-t border-border pt-4 text-xs text-muted-foreground">
            <p className="truncate">{user?.full_name ?? "User"}</p>
            <p className="truncate">{user?.email ?? "No email"}</p>
          </div>
        ) : null}
      </div>
    </aside>
  );
}
