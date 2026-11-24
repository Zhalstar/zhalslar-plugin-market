<script setup lang="ts">
import { GitFork, Link2, Unlink } from "@lucide/vue";
import { computed, onMounted, ref } from "vue";
import { api } from "../api";
import { t } from "../preferences";
import type { OAuthAccount } from "../types";

const accounts = ref<OAuthAccount[]>([]);
const loading = ref(true);
const action = ref("");
const error = ref("");
const linked = computed(() => new Map(accounts.value.map((item) => [item.provider, item])));

const load = async () => {
  loading.value = true;
  try {
    accounts.value = await api.accounts();
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : t("actionFailed");
  } finally {
    loading.value = false;
  }
};

const connect = async (provider: string) => {
  action.value = provider;
  error.value = "";
  try {
    const result = await api.connect(provider);
    window.location.assign(result.url);
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : t("actionFailed");
    action.value = "";
  }
};

const unlink = async (provider: string) => {
  action.value = provider;
  error.value = "";
  try {
    await api.unlink(provider);
    await load();
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : t("actionFailed");
  } finally {
    action.value = "";
  }
};

onMounted(load);
</script>

<template>
  <main class="page-shell accounts-page">
    <h1 class="page-heading">{{ t('accounts') }}</h1>
    <p class="page-subtitle">{{ t('accountsHint') }}</p>
    <v-alert v-if="error" type="error" variant="tonal" class="mt-5">{{ error }}</v-alert>
    <v-progress-linear v-if="loading" indeterminate color="primary" class="mt-6" />
    <div v-else class="account-list">
      <section v-for="provider in ['github', 'gitee']" :key="provider" class="account-row panel">
        <div class="provider-icon">
          <GitFork v-if="provider === 'github'" :size="25" />
          <span v-else class="gitee-mark">G</span>
        </div>
        <div class="account-copy">
          <h2>{{ provider === "github" ? "GitHub" : "Gitee" }}</h2>
          <p v-if="linked.get(provider as 'github' | 'gitee')">
            {{ t('linked', { name: linked.get(provider as 'github' | 'gitee')?.username || '' }) }}
          </p>
          <p v-else>{{ t('unlinked') }}</p>
        </div>
        <v-btn
          v-if="linked.get(provider as 'github' | 'gitee')"
          color="error"
          variant="text"
          :loading="action === provider"
          @click="unlink(provider)"
        >
          <span class="action-content"><Unlink :size="17" />{{ t('unlink') }}</span>
        </v-btn>
        <v-btn v-else color="primary" variant="tonal" :loading="action === provider" @click="connect(provider)">
          <span class="action-content"><Link2 :size="17" />{{ t('connect') }}</span>
        </v-btn>
      </section>
    </div>
  </main>
</template>

<style scoped>
.accounts-page {
  max-width: 850px;
}

.account-list {
  display: grid;
  gap: 12px;
  margin-top: 25px;
}

.account-row {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 19px 22px;
}

.provider-icon {
  display: grid;
  width: 42px;
  height: 42px;
  flex: 0 0 42px;
  border: 1px solid var(--line);
  border-radius: 8px;
  place-items: center;
}

.gitee-mark {
  color: rgb(var(--v-theme-error));
  font-size: 21px;
  font-weight: 800;
}

.account-copy {
  min-width: 0;
  flex: 1;
}

.account-copy h2 {
  margin: 0 0 3px;
  font-size: 15px;
}

.account-copy p {
  margin: 0;
  color: var(--muted);
  font-size: 13px;
}
</style>
