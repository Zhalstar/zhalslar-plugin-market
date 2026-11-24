import { ref, watch } from "vue";
import en from "./locales/en-US.json";
import zh from "./locales/zh-CN.json";

const messages = { "en-US": en, "zh-CN": zh };
export const language = ref<keyof typeof messages>(localStorage.getItem("zhalhub-language") === "en-US" ? "en-US" : "zh-CN");
export const appearance = ref<"marketLight" | "marketDark">(localStorage.getItem("zhalhub-theme") === "marketDark" ? "marketDark" : "marketLight");

watch(language, (value) => {
  localStorage.setItem("zhalhub-language", value);
  document.documentElement.lang = value;
}, { immediate: true });
watch(appearance, (value) => localStorage.setItem("zhalhub-theme", value));

export function t(key: keyof typeof en, values: Record<string, string | number> = {}): string {
  return messages[language.value][key].replace(/\{(\w+)\}/g, (_, name) => String(values[name] ?? ""));
}
