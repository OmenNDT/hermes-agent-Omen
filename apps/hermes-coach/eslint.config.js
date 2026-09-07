import js from "@eslint/js";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import tseslint from "typescript-eslint";
import { defineConfig, globalIgnores } from "eslint/config";

export default defineConfig([
  globalIgnores(["dist"]),
  {
    files: ["**/*.{ts,tsx}"],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      ecmaVersion: 2023,
      globals: globals.browser,
    },
    rules: {
      // Product rules, not style. Each one guards an invariant the plan states
      // and that a reviewer would otherwise have to catch by eye.
      "no-restricted-globals": [
        "error",
        {
          name: "localStorage",
          message:
            "Coach records live in server-side SQLite. Browser storage is for ephemeral UI preferences only.",
        },
        {
          name: "sessionStorage",
          message:
            "Coach records live in server-side SQLite. Browser storage is for ephemeral UI preferences only.",
        },
      ],
      "no-restricted-properties": [
        "error",
        {
          object: "navigator",
          property: "mediaDevices",
          message: "Coach ships no voice or microphone surface.",
        },
      ],
      "no-restricted-syntax": [
        "error",
        {
          selector:
            "NewExpression[callee.name='SpeechRecognition'], NewExpression[callee.name='MediaRecorder']",
          message: "Coach ships no voice or microphone surface.",
        },
      ],
    },
  },
  {
    // Tests legitimately reach for storage to prove the app never writes to it.
    files: ["**/*.test.{ts,tsx}"],
    rules: { "no-restricted-globals": "off" },
  },
]);
