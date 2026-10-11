import type { SVGProps } from "react";

const paths: Record<string, string> = {
  check: "M5 12.5l4.2 4.2L19 7",
  alert: "M12 8v5m0 3.5v.01M10.3 4.2L2.9 17a2 2 0 001.7 3h14.8a2 2 0 001.7-3L13.7 4.2a2 2 0 00-3.4 0z",
  cross: "M6 6l12 12M18 6L6 18",
  plug: "M9 3v5m6-5v5M7 8h10v3a5 5 0 01-10 0V8zm5 8v5",
  upload: "M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5M4 16v3a1 1 0 001 1h14a1 1 0 001-1v-3",
  file: "M7 3h7l5 5v12a1 1 0 01-1 1H7a1 1 0 01-1-1V4a1 1 0 011-1zm7 0v5h5",
  chevron: "M9 6l6 6-6 6",
  arrow: "M5 12h14m0 0l-5-5m5 5l-5 5",
  close: "M6 6l12 12M18 6L6 18",
  sliders: "M4 7h9m4 0h3M4 17h3m4 0h9M13 4v6m-6 4v6",
  info: "M12 11v5m0-8.5v.01M12 21a9 9 0 100-18 9 9 0 000 18z",
  refresh: "M20 11a8 8 0 10-.9 4M20 5v6h-6",
  table: "M4 5h16v14H4zM4 10h16M10 5v14",
  chart: "M4 19V5m0 14h16M8 15l3-4 3 2 5-6",
};

export function Icon({ name, size = 18, ...rest }: { name: keyof typeof paths; size?: number } & SVGProps<SVGSVGElement>) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...rest}
    >
      <path d={paths[name]} />
    </svg>
  );
}
