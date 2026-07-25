import type { Config } from "tailwindcss";

/**
 * Design tokens extracted directly from the "Trust Core" Figma file
 * (ERP Project — Page 1) via the Figma Plugin API, not eyeballed from
 * screenshots. Values reflect what's actually bound to nodes across all
 * 9 screens (Login, Dashboard, Contacts Directory, Contact Detail,
 * Financial Core, Transactions, Compliance, Reports, Plugins Marketplace,
 * Settings).
 *
 * Pairs with: frontend_architecture_guide-v2.md
 * (Next.js App Router + Tailwind CSS + Shadcn UI + RTL-first Arabic)
 */
const config: Config = {
  darkMode: "class",
  content: [
    "./src/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Sidebar / primary surface — near-black navy, NOT pure black
        ink: {
          DEFAULT: "#040D1B", // sidebar background, page headings
          50: "#F4F5F7",
          100: "#E8EAEE",
          400: "#75777D", // secondary text on light surfaces
          500: "#45474C", // primary body text on light surfaces
          600: "#1B1B1D", // strong text / high-emphasis labels
        },

        // Single accent color across the whole product (buttons, active
        // states, links, highlights). #8B5000 was the old value — every
        // instance has been swapped to #FF9800.
        accent: {
          DEFAULT: "#FF9800",
          hover: "#E6890A",   // ~10% darker, for :hover / :active states
          border: "#653900",  // active sidebar item left-border accent
          tint: "#FFF3E0",    // light background tint (badges, hovers)
        },

        // Neutral / "paper" family — backgrounds, borders, dividers
        paper: {
          DEFAULT: "#FCF8FA", // app background
          card: "#FFFFFF",    // card / panel surfaces
          subtle: "#F6F3F4",  // table header bg, secondary surfaces
          border: "#C5C6CC",  // default border
          "border-soft": "#E4E2E3", // hairline / low-emphasis border
        },

        // Sidebar-specific text colors (on the dark #040D1B surface)
        sidebar: {
          DEFAULT: "#040D1B",
          text: "#BEC7DB",     // nav link text (inactive)
          subtitle: "#818A9D", // "نظام إدارة المؤسسات" under the logo
          "text-active": "#FFFFFF",
        },

        // Semantic / status colors — used ONLY for status pills, badges,
        // and financial +/- indicators. Never used decoratively.
        success: {
          DEFAULT: "#2E7D32",
          bg: "#E8F5E9",
        },
        danger: {
          DEFAULT: "#BA1A1A",
          bg: "#FFEBEE",
        },
        warning: {
          DEFAULT: "#F9A825",
          bg: "#FFFDE7",
        },
      },

      fontFamily: {
        // Single bilingual family for Arabic + Latin UI text
        sans: ["IBM Plex Sans Arabic", "IBM Plex Sans", "sans-serif"],
        // Numeric / currency figures — always rendered LTR even in RTL context
        mono: ["JetBrains Mono", "IBM Plex Mono", "monospace"],
      },

      fontSize: {
        xs: "10px",
        "xs-plus": "11px",
        sm: "12px",
        base: "14px",
        md: "16px",
        lg: "20px",
        xl: "28px",
        "2xl": "30px",
      },

      borderRadius: {
        none: "0px",
        sm: "2px",
        DEFAULT: "4px",
        md: "8px",
        lg: "12px",
        xl: "16px",
      },
    },
  },
  plugins: [],
};

export default config;
