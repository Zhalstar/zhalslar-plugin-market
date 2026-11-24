<script setup lang="ts">
import { ChevronDown, ChevronLeft, ChevronRight, RefreshCw, Search, Store } from "@lucide/vue";
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { api } from "../api";
import MarketWelcome from "../components/MarketWelcome.vue";
import PluginCard from "../components/PluginCard.vue";
import { t } from "../preferences";
import type { Plugin } from "../types";

const route = useRoute();
const router = useRouter();
const pageSizes = computed(() => [9, 18, 27, 0].map((value) => ({ value, title: value ? String(value) : t("unlimited") })));
const sortOptions = computed(() => [
  { value: "updated", title: t("sortUpdated") },
  { value: "newest", title: t("sortNewest") },
  { value: "stars", title: t("sortStars") },
  { value: "name", title: t("sortName") },
]);
const providerOptions = computed(() => [
  { value: "", title: t("all") },
  { value: "github", title: "GitHub" },
  { value: "gitee", title: "Gitee" },
]);
const pageSize = computed(() => pageSizes.value.find(({ value }) => String(value) === route.query.size)?.value ?? 9);
const sort = computed(() => sortOptions.value.find(({ value }) => value === route.query.sort)?.value ?? "updated");
const plugins = ref<Plugin[]>([]);
const total = ref(0);
const pages = computed(() => pageSize.value ? Math.max(1, Math.ceil(total.value / pageSize.value)) : 1);
const page = computed(() => {
  if (!pageSize.value) return 1;
  const value = Number(route.query.page);
  return Number.isInteger(value) && value > 0 && value <= 1_000_000 ? value : 1;
});
const searchQuery = computed(() => typeof route.query.search === "string" ? route.query.search.slice(0, 100) : "");
const search = ref(searchQuery.value);
const provider = computed(() => route.query.provider === "github" || route.query.provider === "gitee" ? route.query.provider : "");
const loading = ref(true);
const error = ref("");
const refresh = ref(0);

watch(searchQuery, (value) => { search.value = value; });
watch(search, (value, _, onCleanup) => {
  const term = value.trim();
  if (term === searchQuery.value) return;
  const timer = setTimeout(() => {
    void router.replace({ query: { ...route.query, search: term || undefined, page: undefined } });
  }, 240);
  onCleanup(() => clearTimeout(timer));
});

watch([page, pageSize, sort, searchQuery, provider, refresh], async ([number, size, order, term, host], _, onCleanup) => {
  const controller = new AbortController();
  onCleanup(() => controller.abort());
  loading.value = true;
  error.value = "";
  try {
    const result = await api.listPlugins(number, size, order, term, host, controller.signal);
    if (controller.signal.aborted) return;
    total.value = result.total;
    plugins.value = result.items;
    if (number > pages.value) {
      await router.replace({ query: { ...route.query, page: pages.value > 1 ? String(pages.value) : undefined } });
    }
  } catch (reason) {
    if (!controller.signal.aborted) error.value = reason instanceof Error ? reason.message : t("actionFailed");
  } finally {
    if (!controller.signal.aborted) loading.value = false;
  }
}, { immediate: true });
</script>

<template>
  <main class="page-shell market-page">
    <div class="market-heading-row">
      <h1 class="page-heading">{{ t('marketTitle') }}</h1>
      <span v-if="!error" class="market-total" aria-live="polite">{{ total || !loading ? t('count', { count: total }) : '' }}</span>
      <MarketWelcome />
    </div>

    <div class="market-tools">
      <v-text-field v-model="search" variant="outlined" density="compact" hide-details maxlength="100"
        :placeholder="t('search')" :aria-label="t('search')" class="market-search">
        <template #prepend-inner><Search :size="18" /></template>
      </v-text-field>
      <v-select :model-value="sort" :items="sortOptions" :label="t('sort')" :menu-icon="ChevronDown" variant="outlined" density="compact" hide-details
        @update:model-value="router.push({ query: { ...route.query, sort: $event === 'updated' ? undefined : $event, page: undefined } })" />
      <v-select :model-value="provider" :items="providerOptions" :label="t('source')" :menu-icon="ChevronDown" variant="outlined" density="compact" hide-details
        @update:model-value="router.push({ query: { ...route.query, provider: $event || undefined, page: undefined } })" />
      <v-select :model-value="pageSize" :items="pageSizes" :label="t('pageSize')" :menu-icon="ChevronDown" variant="outlined" density="compact" hide-details
        @update:model-value="router.push({ query: { ...route.query, size: $event === 9 ? undefined : String($event), page: undefined } })" />
      <v-btn icon size="40" variant="text" class="market-refresh" :title="t('refresh')" :aria-label="t('refresh')" :loading="loading" @click="refresh++">
        <RefreshCw :size="17" />
      </v-btn>
    </div>

    <v-alert v-if="error" type="error" variant="tonal" class="mb-5">{{ error }}</v-alert>
    <div v-else-if="loading" class="plugin-grid" :aria-label="t('loading')">
      <v-skeleton-loader v-for="item in 9" :key="item" type="article" class="panel" />
    </div>
    <div v-else-if="plugins.length" class="plugin-grid">
      <PluginCard v-for="plugin in plugins" :key="plugin.id" :plugin="plugin" :market-query="route.query" />
    </div>
    <div v-else class="empty-state">
      <div>
        <Store :size="32" />
        <p>{{ t('noResults') }}</p>
      </div>
    </div>
    <v-pagination v-if="pages > 1 && !error" :model-value="page" :length="pages" density="compact" class="market-pagination"
      :aria-label="t('pagination')" :previous-aria-label="t('previousPage')" :next-aria-label="t('nextPage')"
      :prev-icon="ChevronLeft" :next-icon="ChevronRight"
      :page-aria-label="t('pageNumber', { page: '{0}' })" :current-page-aria-label="t('currentPage', { page: '{0}' })"
      @update:model-value="router.push({ query: { ...route.query, page: $event > 1 ? String($event) : undefined } })" />
  </main>
</template>

<style scoped>
.market-heading-row {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 4px 12px;
}

.market-total {
  color: var(--muted);
  font-size: 13px;
}

.market-tools {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 150px 112px 112px 40px;
  align-items: center;
  gap: 10px;
  margin: 18px 0 20px;
}

.market-tools :deep(.v-field) {
  background: var(--panel);
  border-radius: 8px;
  font-size: 13px;
}

.market-tools :deep(.v-field__outline) {
  --v-field-border-opacity: 0.2;
}

.market-tools :deep(.v-field--focused .v-field__outline) {
  --v-field-border-opacity: 1;
}

.market-tools :deep(.v-field__append-inner .v-icon) {
  font-size: 16px;
}

.market-refresh {
  color: var(--muted);
}

.market-pagination {
  margin-top: 20px;
}

@media (max-width: 760px) {
  .market-tools {
    grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr) minmax(0, 1fr);
    gap: 12px 8px;
  }

  .market-search {
    grid-column: 1 / -1;
    grid-row: 1;
    margin-right: 48px;
  }

  .market-refresh {
    grid-column: 3;
    grid-row: 1;
    justify-self: end;
  }

  .market-tools :deep(.v-select .v-field) {
    --v-field-padding-start: 8px;
    --v-field-padding-end: 0px;
    padding-inline-end: 6px;
  }

  .market-tools :deep(.v-select .v-field__append-inner .v-icon) {
    margin-inline-start: 2px;
    font-size: 14px;
  }
}
</style>
