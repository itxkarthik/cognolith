"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { type FormEvent, useEffect, useState, useSyncExternalStore } from "react";
import { motion, useMotionValue, useMotionValueEvent, useReducedMotion, useScroll, useSpring } from "motion/react";
import { useTheme } from "next-themes";
import { Bell, LogOut, MoonStar, Search, Settings, SunMedium, User } from "lucide-react";

import { useAuth } from "@/lib/hooks/useAuth";
import {
  Button,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  Input,
} from "@/components/ui";
import { cn } from "@/lib/utils/cn";

interface HeaderProps {
  sidebarExpanded: boolean;
}

interface AccountMenuProps {
  isLoggingOut: boolean;
  onLogout: () => Promise<void>;
  onOpenProfile: () => void;
}

const PAGE_TITLES = [
  ["/dashboard/knowledge-graph", "Knowledge graph"],
  ["/dashboard/documents", "Documents"],
  ["/dashboard/notes", "Notes"],
  ["/dashboard/chat", "Chat"],
  ["/dashboard/search", "Search"],
  ["/dashboard/settings", "Settings"],
  ["/dashboard/support", "Support"],
] as const;

function getPageTitle(pathname: string) {
  return PAGE_TITLES.find(([route]) => pathname.startsWith(route))?.[1] ?? "Dashboard";
}

function AccountMenu({ isLoggingOut, onLogout, onOpenProfile }: AccountMenuProps) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="icon" className="border-border bg-background" aria-label="Open account menu">
          <Settings className="h-4 w-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-52">
        <DropdownMenuItem onClick={onOpenProfile}>
          <User className="mr-2 h-4 w-4" />
          Profile
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          onClick={() => {
            void onLogout();
          }}
          variant="destructive"
        >
          <LogOut className="mr-2 h-4 w-4" />
          {isLoggingOut ? "Logging out..." : "Logout"}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function Header({ sidebarExpanded }: HeaderProps) {
  const pathname = usePathname();
  const router = useRouter();
  const { logout } = useAuth();
  const { theme, setTheme, resolvedTheme } = useTheme();
  const { scrollY } = useScroll();
  const reduceMotion = useReducedMotion();
  const mobileHeaderY = useMotionValue(0);
  const mobileHeaderSpringY = useSpring(mobileHeaderY, { stiffness: 420, damping: 42 });
  const [searchQuery, setSearchQuery] = useState("");
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const mounted = useSyncExternalStore(
    () => () => undefined,
    () => true,
    () => false
  );

  useEffect(() => {
    mobileHeaderY.set(0);
  }, [mobileHeaderY, pathname]);

  useMotionValueEvent(scrollY, "change", (latest) => {
    if (typeof window === "undefined" || window.innerWidth >= 1024) return;

    const previous = scrollY.getPrevious() ?? latest;
    const nextY = latest < 72 || latest < previous ? 0 : -56;
    if (nextY !== mobileHeaderY.get()) mobileHeaderY.set(nextY);
  });

  const currentTheme = theme === "system" ? resolvedTheme : theme;

  const toggleTheme = () => {
    setTheme(currentTheme === "dark" ? "light" : "dark");
  };

  const submitSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const query = searchQuery.trim();
    router.push(query ? `/dashboard/search?q=${encodeURIComponent(query)}` : "/dashboard/search");
  };

  const handleLogout = async () => {
    if (isLoggingOut) return;
    setIsLoggingOut(true);
    try {
      await logout();
      router.replace("/auth/login");
    } finally {
      setIsLoggingOut(false);
    }
  };

  const accountMenuProps = {
    isLoggingOut,
    onLogout: handleLogout,
    onOpenProfile: () => router.push("/dashboard/settings"),
  };

  return (
    <>
      <header
        className={cn(
          "fixed left-0 right-0 top-0 z-20 hidden border-b border-border bg-background transition-[left] duration-200 lg:block",
          sidebarExpanded ? "lg:left-64" : "lg:left-16"
        )}
      >
        <div className="flex h-16 items-center gap-4 px-6">
          <form onSubmit={submitSearch} className="relative min-w-0 max-w-2xl flex-1">
            <Button
              type="submit"
              variant="ghost"
              size="icon"
              className="absolute left-px top-1/2 z-10 h-9 w-9 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              aria-label="Submit search"
            >
              <Search className="h-4 w-4" />
            </Button>
            <Input
              aria-label="Search notes, documents, and chats"
              className="pl-10"
              placeholder="Search notes, documents, and chats"
              type="search"
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
            />
          </form>

          <div className="ml-auto flex items-center gap-2">
            <Button
              variant="outline"
              size="icon"
              className="border-border bg-background"
              onClick={toggleTheme}
              aria-label="Toggle theme"
            >
              {mounted && currentTheme === "dark" ? <SunMedium className="h-4 w-4" /> : <MoonStar className="h-4 w-4" />}
            </Button>

            <Button variant="outline" size="icon" className="border-border bg-background" aria-label="Notifications">
              <Bell className="h-4 w-4" />
            </Button>

            <AccountMenu {...accountMenuProps} />
          </div>
        </div>
      </header>

      <motion.header
        initial={false}
        style={{ y: reduceMotion ? mobileHeaderY : mobileHeaderSpringY }}
        className="fixed inset-x-0 top-0 z-20 border-b border-border bg-background lg:hidden"
      >
        <div className="flex h-14 items-center gap-2 px-3">
          <Link href="/dashboard" className="flex min-w-0 flex-1 items-center gap-2" aria-label="Open dashboard">
            <span className="shrink-0 text-sm font-bold text-foreground">Cognolith</span>
            <span className="h-4 w-px shrink-0 bg-border" aria-hidden="true" />
            <span className="truncate text-xs text-muted-foreground">{getPageTitle(pathname)}</span>
          </Link>

          <Button asChild variant="outline" size="icon" className="border-border bg-background">
            <Link href="/dashboard/search" aria-label="Open search">
              <Search className="h-4 w-4" />
            </Link>
          </Button>

          <Button
            variant="outline"
            size="icon"
            className="border-border bg-background"
            onClick={toggleTheme}
            aria-label="Toggle theme"
          >
            {mounted && currentTheme === "dark" ? <SunMedium className="h-4 w-4" /> : <MoonStar className="h-4 w-4" />}
          </Button>

          <AccountMenu {...accountMenuProps} />
        </div>
      </motion.header>
    </>
  );
}
