import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // Nexus ERP — Material Design 3 token set
        primary: "var(--primary)",
        "on-primary": "var(--on-primary)",
        "primary-container": "var(--primary-container)",
        "on-primary-container": "var(--on-primary-container)",
        "inverse-primary": "var(--inverse-primary)",
        "primary-fixed": "var(--primary-fixed)",
        "primary-fixed-dim": "var(--primary-fixed-dim)",
        "on-primary-fixed": "var(--on-primary-fixed)",
        "on-primary-fixed-variant": "var(--on-primary-fixed-variant)",

        secondary: "var(--secondary)",
        "on-secondary": "var(--on-secondary)",
        "secondary-container": "var(--secondary-container)",
        "on-secondary-container": "var(--on-secondary-container)",
        "secondary-fixed": "var(--secondary-fixed)",
        "secondary-fixed-dim": "var(--secondary-fixed-dim)",
        "on-secondary-fixed": "var(--on-secondary-fixed)",
        "on-secondary-fixed-variant": "var(--on-secondary-fixed-variant)",

        tertiary: "var(--tertiary)",
        "on-tertiary": "var(--on-tertiary)",
        "tertiary-container": "var(--tertiary-container)",
        "on-tertiary-container": "var(--on-tertiary-container)",
        "tertiary-fixed": "var(--tertiary-fixed)",
        "tertiary-fixed-dim": "var(--tertiary-fixed-dim)",
        "on-tertiary-fixed": "var(--on-tertiary-fixed)",
        "on-tertiary-fixed-variant": "var(--on-tertiary-fixed-variant)",

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

        // Legacy semantic aliases kept for a smooth migration
        success: {
          DEFAULT: "var(--success)",
          bg: "var(--success-bg)",
        },
        danger: {
          DEFAULT: "var(--error)",
          bg: "var(--error-container)",
        },
        warning: {
          DEFAULT: "var(--warning)",
          bg: "var(--warning-bg)",
        },
      },
      fontFamily: {
        sans: ["var(--font-inter)", "var(--font-sans)", "IBM Plex Sans Arabic", "IBM Plex Sans", "sans-serif"],
        headline: ["var(--font-manrope)", "var(--font-sans)", "IBM Plex Sans Arabic", "sans-serif"],
        mono: ["var(--font-mono)", "JetBrains Mono", "IBM Plex Mono", "monospace"],
        "headline-lg": ["var(--font-manrope)", "var(--font-sans)", "sans-serif"],
        "headline-md": ["var(--font-manrope)", "var(--font-sans)", "sans-serif"],
        "headline-sm": ["var(--font-manrope)", "var(--font-sans)", "sans-serif"],
        "body-lg": ["var(--font-inter)", "var(--font-sans)", "sans-serif"],
        "body-md": ["var(--font-inter)", "var(--font-sans)", "sans-serif"],
        "body-sm": ["var(--font-inter)", "var(--font-sans)", "sans-serif"],
        "data-mono": ["var(--font-mono)", "monospace"],
        "label-caps": ["var(--font-inter)", "var(--font-sans)", "sans-serif"],
      },
      fontSize: {
        "headline-lg": ["28px", { lineHeight: "36px", letterSpacing: "-0.02em", fontWeight: "700" }],
        "headline-md": ["20px", { lineHeight: "28px", letterSpacing: "-0.01em", fontWeight: "600" }],
        "headline-sm": ["16px", { lineHeight: "24px", fontWeight: "600" }],
        "body-lg": ["16px", { lineHeight: "24px", fontWeight: "400" }],
        "body-md": ["14px", { lineHeight: "20px", fontWeight: "400" }],
        "body-sm": ["12px", { lineHeight: "16px", fontWeight: "400" }],
        "data-mono": ["14px", { lineHeight: "20px", fontWeight: "600" }],
        "label-caps": ["11px", { lineHeight: "16px", letterSpacing: "0.05em", fontWeight: "700" }],
      },
      borderRadius: {
        sm: "0.25rem",
        DEFAULT: "0.25rem",
        md: "0.5rem",
        lg: "0.5rem",
        xl: "0.75rem",
        "2xl": "1rem",
        full: "9999px",
      },
      spacing: {
        base: "4px",
        "compact-padding": "8px",
        gutter: "16px",
        "card-padding": "20px",
        "container-margin": "24px",
      },
      boxShadow: {
        card: "0px 4px 12px rgba(0,0,0,0.03)",
        overlay: "0px 10px 30px rgba(0,0,0,0.08)",
      },
    },
  },
  plugins: [],
};
export default config;
