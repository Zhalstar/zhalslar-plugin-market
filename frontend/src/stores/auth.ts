import { defineStore } from "pinia";
import { api } from "../api";
import type { User } from "../types";

let initialization: Promise<void> | undefined;

export const useAuthStore = defineStore("auth", {
  state: () => ({
    user: null as User | null,
    initialized: false,
  }),
  actions: {
    async initialize() {
      if (this.initialized) return;
      initialization ??= api.me().then((user) => { this.user = user; }).catch(() => {
        this.user = null;
      }).finally(() => {
        this.initialized = true;
        initialization = undefined;
      });
      await initialization;
    },
    async login(email: string, password: string) {
      this.user = await api.login({ email, password });
    },
    async register(email: string, password: string, displayName: string) {
      this.user = await api.register({ email, password, display_name: displayName });
    },
    async logout() {
      await api.logout();
      this.user = null;
    },
  },
});

