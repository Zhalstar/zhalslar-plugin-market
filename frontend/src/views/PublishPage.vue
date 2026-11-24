<script setup lang="ts">
import { CheckCircle2, GitFork, PackagePlus, RefreshCw, Search } from "@lucide/vue";
import { computed, onMounted, ref, watch } from "vue";
import { api } from "../api";
import { t } from "../preferences";
import type { OAuthAccount, Repository } from "../types";

const accounts = ref<OAuthAccount[]>([]);
const provider = ref<"github" | "gitee">("github");
const repositories = ref<Repository[]>([]);
const selectedIds = ref<string[]>([]);
const search = ref<string | null>("");
const loadingAccounts = ref(true);
const loadingRepositories = ref(false);
const publishing = ref(false);
const error = ref("");
const batchSize = ref(0);
const results = ref<({ repository: Repository } & ({ pluginId: string } | { error: string }))[]>([]);
const connectedProviders = computed(() => new Set(accounts.value.map((item) => item.provider)));
const visibleRepositories = computed(() => {
  const query = search.value?.trim().toLowerCase() || "";
  return repositories.value.filter((item) => item.full_name.toLowerCase().includes(query));
});
const visibleIds = computed(() => new Set(visibleRepositories.value.map((item) => item.id)));
const visibleSelectedCount = computed(() => selectedIds.value.filter((id) => visibleIds.value.has(id)).length);
const successCount = computed(() => results.value.filter((item) => "pluginId" in item).length);

const toggleVisible = (checked: boolean | null) => {
  selectedIds.value = checked
    ? [...new Set([...selectedIds.value, ...visibleIds.value])]
    : selectedIds.value.filter((id) => !visibleIds.value.has(id));
};

const loadRepositories = async () => {
  if (publishing.value || loadingRepositories.value) return;
  repositories.value = [];
  selectedIds.value = [];
  search.value = "";
  results.value = [];
  error.value = "";
  if (!connectedProviders.value.has(provider.value)) return;
  loadingRepositories.value = true;
  try {
    repositories.value = await api.repositories(provider.value);
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : t("actionFailed");
  } finally {
    loadingRepositories.value = false;
  }
};

const publish = async () => {
  if (publishing.value || loadingRepositories.value || !selectedIds.value.length) return;
  const ids = new Set(selectedIds.value);
  const batch = repositories.value.filter((item) => ids.has(item.id));
  if (!batch.length) return;
  const batchProvider = provider.value;
  publishing.value = true;
  error.value = "";
  results.value = [];
  batchSize.value = batch.length;
  try {
    for (const repository of batch) {
      try {
        const plugin = await api.publish(batchProvider, repository.id);
        results.value.push({ repository, pluginId: plugin.id });
        selectedIds.value = selectedIds.value.filter((id) => id !== repository.id);
      } catch (reason) {
        results.value.push({ repository, error: reason instanceof Error ? reason.message : t("actionFailed") });
      }
    }
  } finally {
    publishing.value = false;
  }
};

watch(provider, loadRepositories);
onMounted(async () => {
  try {
    accounts.value = await api.accounts();
    if (!connectedProviders.value.has(provider.value) && accounts.value.length) {
      provider.value = accounts.value[0].provider;
    } else {
      await loadRepositories();
    }
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : t("actionFailed");
  } finally {
    loadingAccounts.value = false;
  }
});
</script>

<template>
  <main class="page-shell publish-page">
    <h1 class="page-heading">{{ t('publishPlugin') }}</h1>
    <p class="page-subtitle">{{ t('publishHint') }}</p>

    <section class="publish-panel panel">
      <v-progress-linear v-if="loadingAccounts" indeterminate color="primary" />
      <template v-else>
        <div class="form-section">
          <label>{{ t('provider') }}</label>
          <v-btn-toggle v-model="provider" mandatory color="primary" variant="outlined" :disabled="publishing || loadingRepositories">
            <v-btn value="github"><span class="action-content"><GitFork :size="17" />GitHub</span></v-btn>
            <v-btn value="gitee"><span class="gitee-inline">G</span>Gitee</v-btn>
          </v-btn-toggle>
          <v-alert v-if="!connectedProviders.has(provider)" type="info" variant="tonal" density="compact">
            {{ t('linkFirst', { provider: provider === 'github' ? 'GitHub' : 'Gitee' }) }}
            <template #append><v-btn to="/settings/accounts" variant="text" size="small">{{ t('goLink') }}</v-btn></template>
          </v-alert>
        </div>

        <div v-if="connectedProviders.has(provider)" class="form-section">
          <div class="field-label-row">
            <label for="repository-search">{{ t('publicRepo') }}</label>
            <v-btn icon variant="text" size="small" :title="t('refreshRepos')" :aria-label="t('refreshRepos')"
              :disabled="publishing || loadingRepositories" @click="loadRepositories">
              <RefreshCw :size="17" />
            </v-btn>
          </div>
          <v-text-field
            id="repository-search"
            v-model="search"
            :placeholder="t('searchRepos')"
            :aria-label="t('searchRepos')"
            :loading="loadingRepositories"
            :disabled="loadingRepositories || publishing"
            variant="outlined"
            density="compact"
            hide-details
            clearable
          >
            <template #prepend-inner><Search :size="17" /></template>
          </v-text-field>
          <div v-if="repositories.length" class="field-label-row selection-toolbar">
            <v-checkbox-btn
              :model-value="visibleSelectedCount > 0 && visibleSelectedCount === visibleRepositories.length"
              :indeterminate="visibleSelectedCount > 0 && visibleSelectedCount < visibleRepositories.length"
              :disabled="publishing || !visibleRepositories.length"
              :label="t(search?.trim() ? 'selectMatchingRepos' : 'selectAll')"
              color="primary" density="compact" @update:model-value="toggleVisible"
            />
            <span>{{ t('reposSelected', { count: selectedIds.length }) }}</span>
          </div>
          <div v-if="visibleRepositories.length" class="repository-list">
            <v-checkbox-btn v-for="item in visibleRepositories" :key="item.id" v-model="selectedIds" :value="item.id"
              :disabled="publishing" :label="item.full_name" color="primary" density="compact" class="repository-option" />
          </div>
          <p v-else-if="!loadingRepositories && !error" class="repository-empty">{{ t('noReposFound') }}</p>
        </div>

        <v-alert v-if="error" type="error" variant="tonal" density="compact" class="mb-5">{{ error }}</v-alert>

        <div v-if="connectedProviders.has(provider)" class="publish-actions">
          <v-btn
            color="primary"
            size="large"
            :disabled="!selectedIds.length || loadingRepositories || publishing"
            :loading="publishing"
            @click="publish"
          >
            <span class="action-content"><PackagePlus :size="18" />{{ t('publishSelected', { count: selectedIds.length }) }}</span>
          </v-btn>
        </div>

        <section v-if="publishing || results.length" class="publish-results" aria-labelledby="publish-result-heading">
          <h2 id="publish-result-heading" aria-live="polite">{{ publishing
            ? t('publishingProgress', { done: results.length, total: batchSize })
            : t('publishSummary', { success: successCount, failed: results.length - successCount }) }}</h2>
          <v-progress-linear v-if="publishing" :model-value="100 * results.length / batchSize" color="primary" />
          <ul v-if="results.length" class="result-list">
            <li v-for="item in results" :key="item.repository.id">
              <router-link v-if="'pluginId' in item" :to="`/plugins/${item.pluginId}`">{{ item.repository.full_name }}</router-link>
              <template v-else>
                <span>{{ item.repository.full_name }}</span>
                <small>{{ item.error }}</small>
              </template>
            </li>
          </ul>
        </section>
      </template>
    </section>
  </main>
</template>

<style scoped>
.publish-page {
  max-width: 820px;
}

.publish-panel {
  margin-top: 25px;
  padding: 26px;
}

.form-section {
  display: grid;
  gap: 11px;
  margin-bottom: 24px;
}

.form-section > label,
.field-label-row label {
  color: var(--ink);
  font-size: 13px;
  font-weight: 700;
}

.field-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.gitee-inline {
  margin-right: 7px;
  color: rgb(var(--v-theme-error));
  font-weight: 800;
}

.selection-toolbar {
  gap: 8px;
  color: var(--muted);
  font-size: 13px;
}

.repository-list {
  max-height: 320px;
  overflow: auto;
  border: 1px solid var(--line);
  border-radius: 6px;
}

.repository-option {
  padding: 3px 10px;
}

.repository-option + .repository-option {
  border-top: 1px solid var(--line);
}

.repository-option :deep(.v-label),
.result-list li {
  overflow-wrap: anywhere;
}

.repository-empty {
  color: var(--muted);
  font-size: 14px;
}

.publish-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 26px;
}

.publish-results {
  margin-top: 22px;
  padding-top: 16px;
  border-top: 1px solid var(--line);
}

.publish-results h2 {
  margin-bottom: 8px;
  font-size: 15px;
}

.result-list {
  display: grid;
  gap: 8px;
  padding-inline-start: 20px;
  font-size: 14px;
}

.result-list small {
  display: block;
  color: rgb(var(--v-theme-error));
}
</style>

