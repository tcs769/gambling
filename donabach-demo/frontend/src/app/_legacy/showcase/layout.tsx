import type { Metadata } from "next";
import type { ReactNode } from "react";
import { ShowcasePage } from "@/components/showcase/ShowcasePage";
import { ShowcaseProvider } from "@/lib/showcase";

export const metadata: Metadata = {
  title: "Donabach: a household, its strategies and its wealth",
  description:
    "Four screens on one fictional household: what it has, what a good advisor gets it, where Donabach's advantage comes from, and how the plan adapts when things change.",
};

/**
 * The showcase flow's layout. The provider keeps the household and the strategies chosen on the second screen across the
 * screens (a layout does not remount when you move between its pages). `data-showcase` marks the flow for the one
 * style that applies only inside it (globals.css: focus is scrolled to below the sticky header). The flow is light, like
 * the rest of the demo.
 */
export default function ShowcaseLayout({ children }: { children: ReactNode }) {
  return (
    <ShowcaseProvider>
      <div data-showcase="">
        <ShowcasePage>{children}</ShowcasePage>
      </div>
    </ShowcaseProvider>
  );
}
