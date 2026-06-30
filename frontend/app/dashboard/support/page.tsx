import { Bug, CircleHelp, ExternalLink, GitFork, ListChecks } from "lucide-react";

import { Badge, Button, Card, CardContent, CardHeader, CardTitle } from "@/components/ui";

const repositoryUrl = "https://github.com/itxkarthik/Personal-AI-Knowledge-Assistant";

const supportLinks = [
  {
    title: "Report a bug",
    description: "Create an issue with steps to reproduce the problem.",
    icon: Bug,
    action: "New issue",
    href: `${repositoryUrl}/issues/new?title=%5BBug%5D%20`,
  },
  {
    title: "Request a feature",
    description: "Suggest an improvement or a new workflow.",
    icon: CircleHelp,
    action: "New request",
    href: `${repositoryUrl}/issues/new?title=%5BFeature%5D%20`,
  },
  {
    title: "Browse open issues",
    description: "Check whether a question or problem is already tracked.",
    icon: ListChecks,
    action: "View issues",
    href: `${repositoryUrl}/issues`,
  },
];

export default function SupportPage() {
  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <section className="space-y-2 border-b border-border pb-5">
        <Badge variant="outline">Open source support</Badge>
        <h1 className="text-2xl font-bold text-foreground">Project support</h1>
        <p className="max-w-2xl text-sm text-muted-foreground">
          Support, bug reports, and feature requests are managed through GitHub Issues.
        </p>
      </section>

      <Card className="border-border bg-card">
        <CardHeader className="flex flex-row items-center justify-between gap-4 border-b border-border">
          <div>
            <CardTitle className="flex items-center gap-2">
              <GitFork className="h-4 w-4" />
              Personal AI Knowledge Assistant
            </CardTitle>
            <p className="mt-1 text-sm text-muted-foreground">Source code, documentation, releases, and project history.</p>
          </div>
          <Button asChild variant="outline" className="shrink-0">
            <a href={repositoryUrl} target="_blank" rel="noreferrer">
              Repository
              <ExternalLink />
            </a>
          </Button>
        </CardHeader>
        <CardContent className="divide-y divide-border p-0">
          {supportLinks.map((item) => {
            const Icon = item.icon;
            return (
              <div key={item.title} className="flex flex-col gap-4 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex min-w-0 items-start gap-3">
                  <Icon className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                  <div>
                    <p className="text-sm font-medium text-foreground">{item.title}</p>
                    <p className="mt-1 text-xs text-muted-foreground">{item.description}</p>
                  </div>
                </div>
                <Button asChild variant="outline" size="sm" className="self-start sm:self-auto">
                  <a href={item.href} target="_blank" rel="noreferrer">
                    {item.action}
                    <ExternalLink />
                  </a>
                </Button>
              </div>
            );
          })}
        </CardContent>
      </Card>

      <section className="border border-border bg-muted p-5">
        <h2 className="text-sm font-bold text-foreground">Before posting an issue</h2>
        <div className="mt-3 grid gap-3 text-sm text-muted-foreground md:grid-cols-3">
          <p>Describe what you were trying to do.</p>
          <p>Include steps that reproduce the behavior.</p>
          <p>Add relevant error text, logs, or screenshots.</p>
        </div>
      </section>
    </div>
  );
}
