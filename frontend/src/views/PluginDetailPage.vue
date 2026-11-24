<script setup lang="ts">
import DOMPurify from "dompurify";
import MarkdownIt from "markdown-it";
import { ArrowLeft, Download, ExternalLink } from "@lucide/vue";
import { computed, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { api } from "../api";
import PluginFacts from "../components/PluginFacts.vue";
import { language, t } from "../preferences";
import type { PluginDetail } from "../types";

const route = useRoute();
const plugin = ref<PluginDetail>();
const loading = ref(true);
const error = ref("");
const logoFailed = ref(false);
const tab = ref("docs");
const currentDownload = computed(() => plugin.value?.versions.find((release) =>
  release.version === plugin.value?.version && release.download_url)?.download_url);
const markdown = new MarkdownIt({ html: true, linkify: true });

const rendered = computed(() => {
  const item = plugin.value;
  if (!item) return {};
  return Object.fromEntries(Object.entries(item.documents).map(([key, doc]) => {
    const folder = doc.path.split("/").slice(0, -1).join("/");
    const content = DOMPurify.sanitize(markdown.render(doc.markdown), {
      USE_PROFILES: { html: true },
      FORBID_TAGS: ["style", "form", "input", "button"],
      FORBID_ATTR: ["style"],
      ALLOW_DATA_ATTR: false,
      RETURN_DOM: true,
    });
    if (item.docs_ref && item.provider) {
      const ref = encodeURIComponent(item.docs_ref);
      const repo = item.repo.replace(/\/$/, "");
      const raw = item.provider === "github"
        ? repo.replace("https://github.com/", "https://raw.githubusercontent.com/")
        : `${repo}/raw`;
      for (const element of content.querySelectorAll("a[href], img[src]")) {
        const image = element.tagName === "IMG";
        const attribute = image ? "src" : "href";
        const url = element.getAttribute(attribute);
        if (!url || /^(?:[a-z][\w+.-]*:|\/\/|#)/i.test(url)) continue;
        const directory = folder && !url.startsWith("/") ? `${folder}/` : "";
        try {
          const resolved = new URL(url.replace(/^\//, ""), `${image ? raw : `${repo}/blob`}/${ref}/${directory}`);
          if (resolved.protocol === "https:") element.setAttribute(attribute, resolved.href);
        } catch { /* Ignore malformed repository links. */ }
      }
    }
    return [key, content.innerHTML];
  }));
});

watch(() => String(route.params.id), async (id, _, onCleanup) => {
  let current = true;
  onCleanup(() => { current = false; });
  loading.value = true;
  error.value = "";
  logoFailed.value = false;
  tab.value = "docs";
  try {
    const item = await api.getPlugin(id);
    if (current) plugin.value = item;
  } catch (reason) {
    if (current) error.value = reason instanceof Error ? reason.message : t("actionFailed");
  } finally {
    if (current) loading.value = false;
  }
}, { immediate: true });

const formatDate = (date: string) => new Date(date).toLocaleDateString(language.value);
</script>

<template>
  <main class="page-shell">
    <router-link :to="{ path: '/market', query: route.query }" class="back-link action-content"><ArrowLeft :size="17" />{{ t('back') }}</router-link>
    <v-progress-linear v-if="loading" indeterminate color="primary" class="mt-5" />
    <v-alert v-else-if="error" type="error" variant="tonal" class="mt-5">{{ error }}</v-alert>
    <template v-else-if="plugin">
      <section class="summary">
        <img :src="logoFailed || !plugin.logo ? '/favicon.svg' : plugin.logo" alt="" class="summary__logo" @error="logoFailed = true" />
        <div class="summary__text">
          <h1 class="page-heading">{{ plugin.display_name || plugin.name }}</h1>
          <code>{{ plugin.name }}</code>
        </div>
        <div class="summary__actions">
          <v-btn :href="plugin.repo" target="_blank" rel="noopener" color="primary" variant="tonal">
            <span class="action-content"><ExternalLink :size="16" />{{ t('repo') }}</span>
          </v-btn>
          <v-btn v-if="currentDownload" :href="currentDownload" color="primary">
            <span class="action-content"><Download :size="16" />{{ t('download') }}</span>
          </v-btn>
        </div>
        <PluginFacts :plugin="plugin" show-identity class="summary__facts" />
        <div class="summary__details">
          <p class="summary__description">{{ plugin.desc }}</p>
          <div class="summary__meta">
            <span v-if="plugin.provider">{{ plugin.provider === 'github' ? 'GitHub' : 'Gitee' }}</span>
            <router-link v-if="plugin.publisher_name !== null" :to="`/users/${plugin.owner_id}`">{{ t('publisher') }} {{ plugin.publisher_name || t('guest') }}</router-link>
            <span>{{ t('updatedAt') }} {{ formatDate(plugin.updated_at) }}</span>
          </div>
        </div>
      </section>

      <v-tabs v-model="tab" color="primary" class="detail-tabs">
        <v-tab value="docs">{{ t('docs') }}</v-tab>
        <v-tab value="changelog">{{ t('changelog') }}</v-tab>
        <v-tab value="versions">{{ t('versions') }}</v-tab>
      </v-tabs>

      <section v-if="tab !== 'versions'" class="detail-content">
        <template v-if="tab === 'docs' ? rendered.readme || rendered.guide : rendered.changelog">
          <template v-if="tab === 'docs'">
            <div v-if="rendered.readme" class="markdown-body" v-html="rendered.readme"></div>
            <h2 v-if="rendered.guide && rendered.readme" class="section-heading mt-8 mb-3">{{ t('guide') }}</h2>
            <div v-if="rendered.guide" class="markdown-body" v-html="rendered.guide"></div>
          </template>
          <div v-else class="markdown-body" v-html="rendered.changelog"></div>
        </template>
        <p v-else class="document-note">{{ t(plugin.sync_state === 'pending' ? 'docsPending' : plugin.sync_state === 'failed' ? 'docsFailed' : tab === 'docs' ? 'docsMissing' : 'changelogMissing') }}</p>
      </section>
      <section v-else class="detail-content">
        <ul class="version-list">
          <li v-for="release in plugin.versions" :key="`${release.version}-${release.commit_sha}`" class="version-row">
            <div>
              <strong>{{ release.version }}</strong>
              <v-chip v-if="release.version === plugin.version" size="x-small" color="primary" class="ml-2">{{ t('latest') }}</v-chip>
              <div class="version-meta">{{ formatDate(release.published_at) }} <code v-if="release.commit_sha">· {{ release.commit_sha.slice(0, 8) }}</code><template v-if="release.package_bytes"> · {{ (release.package_bytes / 1024).toLocaleString(language, { maximumFractionDigits: 1 }) }} KiB</template></div>
              <details v-if="release.package_sha256" class="version-hash"><summary>SHA-256</summary><code>{{ release.package_sha256 }}</code></details>
            </div>
            <div class="version-actions">
              <v-btn :href="release.download_url || undefined" :disabled="!release.download_url" variant="tonal" color="primary" size="small">
                <span class="action-content"><Download :size="16" />{{ t('download') }}</span>
              </v-btn>
              <span v-if="!release.download_url" class="version-meta">{{ t('noArchive') }}</span>
            </div>
          </li>
        </ul>
        <p v-if="!plugin.versions.length">{{ t('noArchive') }}</p>
      </section>
    </template>
  </main>
</template>

<style scoped>
.back-link { color: var(--accent); font-size: 14px; }
.summary { display: grid; grid-template-columns: 72px minmax(0, 1fr) auto; gap: 8px 18px; align-items: start; padding: 22px 0 18px; }
.summary__logo { width: 72px; height: 72px; object-fit: contain; grid-row: 1 / 3; }
.summary__text, .summary__details { overflow-wrap: anywhere; }
.summary__facts { grid-column: 2 / -1; }
.summary__details { grid-column: 2 / -1; display: grid; gap: 8px; }
.summary__text code, .summary__meta, .version-meta, .document-note { color: var(--muted); font-size: 13px; }
.summary__meta, .summary__actions { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; }
.summary__description { white-space: pre-line; }
.detail-tabs { border-bottom: 1px solid var(--line); }
.detail-content { max-width: 900px; margin-inline: auto; padding: 20px 0; }
.summary__meta a, .markdown-body :deep(a) { color: var(--accent); text-decoration: underline; }
.markdown-body { overflow-x: auto; overflow-wrap: anywhere; line-height: 1.75; }
.markdown-body :deep(img) { max-width: 100%; height: auto; }
.markdown-body :deep(div[align="center"]), .markdown-body :deep(p[align="center"]) { text-align: center; }
.markdown-body :deep(pre) { overflow-x: auto; padding: 14px; background: var(--soft); border-radius: 6px; }
.markdown-body :deep(p), .markdown-body :deep(pre), .markdown-body :deep(table) { margin: 10px 0; }
.markdown-body :deep(ul), .markdown-body :deep(ol) { padding-inline-start: 24px; }
.markdown-body :deep(table) { border-collapse: collapse; }
.markdown-body :deep(th), .markdown-body :deep(td) { border: 1px solid var(--line); padding: 6px 10px; }
.markdown-body :deep(th) { background: var(--soft); }
.version-list { list-style: none; }
.version-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 12px; padding: 13px 0; align-items: start; border-bottom: 1px solid var(--line); overflow-wrap: anywhere; }
.version-actions { display: grid; gap: 3px; justify-items: end; }
.version-hash { font-size: 12px; color: var(--muted); }
@media (max-width: 650px) {
  .summary { grid-template-columns: 56px minmax(0, 1fr); gap: 12px; }
  .summary__logo { width: 56px; height: 56px; grid-row: auto; }
  .summary__actions, .summary__details, .summary__facts { grid-column: 1 / -1; }
  .summary__facts { column-gap: 8px; }
  .summary__actions { grid-row: 4; }
  .detail-tabs :deep(.v-tab) { padding: 0 10px; min-width: 66px; }
}
</style>
