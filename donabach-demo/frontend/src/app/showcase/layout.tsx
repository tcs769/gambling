import type { Metadata } from "next";
import type { ReactNode } from "react";
import { ShowcasePage } from "@/components/showcase/ShowcasePage";
import { ShowcaseProvider } from "@/lib/showcase";

export const metadata: Metadata = {
  title: "Donabach: a household, its strategies and its wealth",
  description:
    "Three screens on one fictional household: what it has, where Donabach's advantage comes from, and the wealth it builds.",
};

/**
 * The showcase flow's layout. The provider keeps the household and the strategies chosen on the second screen for the
 * third (a layout does not remount when you move between its pages). `data-showcase` is what the dark theme in
 * globals.css looks for: the theme applies while this flow is on the page and nowhere else.
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
