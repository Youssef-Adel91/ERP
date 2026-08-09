import type { Config } from "tailwindcss";

/**
 * Design tokens — Material Design 3 CSS-variable tokens from globals.css
 * plus the original "Trust Core" Figma tokens (ink, accent, paper, sidebar).
 *
 * Pairs with: frontend_architecture_guide-v2.md
 */
const config: Config = {
  darkMode: "class",
  content: [
    "./src/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // ── Material Design 3 CSS-variable tokens (defined in globals.css) ────
        primary: "var(--primary)",
        "on-primary": "var(--on-primary)",
        "primary-container": "var(--primary-container)",
        "on-primary-container": "var(--on-primary-container)",
        "inverse-primary": "var(--inverse-primary)",

        secondary: "var(--secondary)",
        "on-secondary": "var(--on-secondary)",
        "secondary-container": "var(--secondary-container)",
        "on-secondary-container": "var(--on-secondary-container)",

        tertiary: "var(--tertiary)",
        "on-tertiary": "var(--on-tertiary)",
        "tertiary-container": "var(--tertiary-container)",
        "on-tertiary-container": "var(--on-tertiary-container)",

        error: "var(--error)",
        "on-error": "var(--on-error)",
        "error-container": "var(--error-container)",
        "on-error-container": "var(--on-error-container)",

        background: "var(--background)",
        "on-background": "var(--on-background)",

        surface: "var(--surface)",
        "on-surface": "var(--on-surface)",
        "surface-variant": "var(--surface-variant)",
        "on-surface-variant": "var(--on-surface-variant)",
        "surface-dim": "var(--surface-dim)",
        "surface-bright": "var(--surface-bright)",
        "surface-tint": "var(--surface-tint)",
        "surface-container-lowest": "var(--surface-container-lowest)",
        "surface-container-low": "var(--surface-container-low)",
        "surface-container": "var(--surface-container)",
        "surface-container-high": "var(--surface-container-high)",
        "surface-container-highest": "var(--surface-container-highest)",

        "inverse-surface": "var(--inverse-surface)",
        "inverse-on-surface": "var(--inverse-on-surface)",

        outline: "var(--outline)",
        "outline-variant": "var(--outline-variant)",

        // ── Semantic / status ─────────────────────────────────────────────────
        success: { DEFAULT: "var(--success)", bg: "var(--success-bg)" },
        warning: { DEFAULT: "var(--warning)", bg: "var(--warning-bg)" },

        // ── Sidebar / primary surface — near-black navy ───────────────────────
        ink: {
          DEFAULT: "#040D1B",
          50: "#F4F5F7",
          100: "#E8EAEE",
          400: "#75777D",
          500: "#45474C",
          600: "#1B1B1D",
        },

        // ── Single accent color across the whole product ───────────────────────
        accent: {
          DEFAULT: "#FF9800",
          hover: "#E6890A",
          border: "#653900",
          tint: "#FFF3E0",
        },

        // ── Neutral / "paper" family ───────────────────────────────────────────
        paper: {
          DEFAULT: "#FCF8FA",
          card: "#FFFFFF",
          subtle: "#F6F3F4",
          border: "#C5C6CC",
          "border-soft": "#E4E2E3",
        },

        // ── Sidebar-specific text colors ───────────────────────────────────────
        sidebar: {
          DEFAULT: "#040D1B",
          text: "#BEC7DB",
          subtitle: "#818A9D",
          "text-active": "#FFFFFF",
        },
      },

      fontFamily: {
        sans: ["IBM Plex Sans Arabic", "IBM Plex Sans", "sans-serif"],
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
        // Alias used by @apply text-body-md in globals.css
        "body-md": ["14px", { lineHeight: "1.5" }],
      },

      borderRadius: {
        none: "0px",
        sm: "2px",
        DEFAULT: "4px",
        md: "8px",
        lg: "12px",
        xl: "16px",
      },

      boxShadow: {
        // Used by @apply shadow-card in .glass-card
        card: "0 1px 3px 0 rgb(0 0 0 / 0.08), 0 1px 2px -1px rgb(0 0 0 / 0.06)",
      },
    },
  },
  plugins: [],
};

export default config;
