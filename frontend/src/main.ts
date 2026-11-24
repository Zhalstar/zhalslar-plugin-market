import "vuetify/styles";
import "./styles.css";

import { Square, SquareCheck, SquareMinus } from "@lucide/vue";
import { createPinia } from "pinia";
import { createApp } from "vue";
import { createVuetify } from "vuetify";
import App from "./App.vue";
import router from "./router";
import { appearance, language } from "./preferences";
import { en, zhHans } from "vuetify/locale";

const vuetify = createVuetify({
  locale: { locale: language.value === "en-US" ? "en" : "zhHans", messages: { en, zhHans } },
  icons: { aliases: { checkboxOff: Square, checkboxOn: SquareCheck, checkboxIndeterminate: SquareMinus } },
  theme: {
    defaultTheme: appearance.value,
    themes: {
      marketLight: {
        dark: false,
        colors: {
          background: "#f6f8fa",
          surface: "#ffffff",
          primary: "#1565c0",
          secondary: "#087f5b",
          error: "#c62828",
          warning: "#ad6800",
        },
      },
      marketDark: {
        dark: true,
        colors: {
          background: "#181a1c",
          surface: "#222528",
          primary: "#93c5fd",
          secondary: "#79d6b4",
          error: "#ffb3b1",
          warning: "#f1c178",
        },
      },
    },
  },
  defaults: {
    VCard: { rounded: "lg", elevation: 0 },
    VBtn: { rounded: "lg" },
    VTextField: { variant: "outlined", density: "comfortable" },
  },
});

createApp(App).use(createPinia()).use(router).use(vuetify).mount("#app");
