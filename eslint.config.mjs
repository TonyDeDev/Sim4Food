import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    // Parked Vite SPA from frontend-design, pending port to App Router.
    "src/*.jsx",
    "src/components/**/*.jsx",
    "src/screens/**/*.jsx",
    "src/utils/**/*.js",
    "vite.config.js",
  ]),
]);

export default eslintConfig;
