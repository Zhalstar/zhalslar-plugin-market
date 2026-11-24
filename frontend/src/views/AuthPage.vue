<script setup lang="ts">
import { LockKeyhole, Mail, UserRound } from "@lucide/vue";
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useAuthStore } from "../stores/auth";
import { t } from "../preferences";

const props = withDefaults(defineProps<{ initialMode?: "login" | "register" }>(), {
  initialMode: "login",
});
const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const mode = ref(props.initialMode);
const email = ref("");
const password = ref("");
const displayName = ref("");
const loading = ref(false);
const error = ref("");
const title = computed(() => t(mode.value === "login" ? "loginTitle" : "registerTitle"));

watch(
  () => route.path,
  () => {
    mode.value = route.path === "/register" ? "register" : "login";
    error.value = "";
  },
);

const submit = async () => {
  loading.value = true;
  error.value = "";
  try {
    if (mode.value === "login") {
      await auth.login(email.value, password.value);
    } else {
      await auth.register(email.value, password.value, displayName.value);
    }
    await router.push(String(route.query.next || "/market"));
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : t("actionFailed");
  } finally {
    loading.value = false;
  }
};
</script>

<template>
  <main class="auth-layout">
    <section class="auth-panel panel">
      <img src="/favicon.svg" alt="" class="auth-logo" />
      <h1>{{ title }}</h1>
      <v-btn-toggle v-model="mode" mandatory color="primary" variant="outlined" class="auth-mode">
        <v-btn value="login" to="/login">{{ t('login') }}</v-btn>
        <v-btn value="register" to="/register">{{ t('register') }}</v-btn>
      </v-btn-toggle>
      <v-alert v-if="error" type="error" variant="tonal" density="compact" class="mb-4">{{ error }}</v-alert>
      <v-form @submit.prevent="submit">
        <v-text-field v-if="mode === 'register'" v-model="displayName" :label="t('displayName')" maxlength="100">
          <template #prepend-inner><UserRound :size="18" /></template>
        </v-text-field>
        <v-text-field v-model="email" :label="t('email')" type="email" autocomplete="email" required>
          <template #prepend-inner><Mail :size="18" /></template>
        </v-text-field>
        <v-text-field
          v-model="password"
          :label="t('password')"
          type="password"
          :autocomplete="mode === 'login' ? 'current-password' : 'new-password'"
          minlength="10"
          required
        >
          <template #prepend-inner><LockKeyhole :size="18" /></template>
        </v-text-field>
        <v-btn type="submit" block color="primary" size="large" :loading="loading">
          {{ t(mode === "login" ? "login" : "register") }}
        </v-btn>
      </v-form>
    </section>
  </main>
</template>

<style scoped>
.auth-layout {
  display: grid;
  min-height: calc(100vh - 63px);
  padding: 44px 16px;
  place-items: start center;
}

.auth-panel {
  width: min(100%, 420px);
  padding: 32px;
}

.auth-logo {
  display: block;
  width: 44px;
  height: 44px;
  margin: 0 auto 15px;
  border-radius: 8px;
}

.auth-panel h1 {
  margin: 0 0 22px;
  font-size: 22px;
  text-align: center;
}

.auth-mode {
  display: grid;
  grid-template-columns: 1fr 1fr;
  width: 100%;
  margin-bottom: 22px;
}

.auth-mode :deep(.v-btn) {
  width: 100%;
}
</style>

