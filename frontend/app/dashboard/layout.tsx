import type { ReactNode } from "react";

import { DashboardLayout } from "@/components/layout/DashboardLayout";

export default function DashboardRootLayout({
	children,
}: {
	children: ReactNode;
}) {
	return (
		<DashboardLayout>
			<div className="mx-auto w-full max-w-7xl">{children}</div>
		</DashboardLayout>
	);
}
