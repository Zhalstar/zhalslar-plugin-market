<script setup lang="ts">
import {
  Boxes,
  Languages,
  Link2,
  LogIn,
  LogOut,
  Menu,
  Moon,
  PackagePlus,
  Store,
  Sun,
  UserRound,
} from "@lucide/vue";
import { ref, watch } from "vue";
import { useRouter } from "vue-router";
import { useLocale, useTheme } from "vuetify";
import UserAvatar from "./components/UserAvatar.vue";
import { appearance, language, t } from "./preferences";
import { useAuthStore } from "./stores/auth";

const auth = useAuthStore();
if (!auth.initialized) void auth.initialize();
const router = useRouter();
const theme = useTheme();
const locale = useLocale();
const menuOpen = ref(false);
watch(appearance, (value) => { theme.global.name.value = value; });
watch(language, (value) => { locale.current.value = value === "en-US" ? "en" : "zhHans"; });

const logout = async () => {
  await auth.logout();
  await router.push("/market");
};
</script>

<template>
  <v-app>
    <header class="app-header">
      <div class="app-header__inner">
        <router-link to="/market" class="brand" aria-label="ZhalHub">
          <img src="/favicon.svg" alt="" class="brand__mark" />
          <span class="brand__name">ZhalHub</span>
        </router-link>

        <nav class="desktop-nav" :aria-label="t('navigation')">
          <router-link to="/market" class="nav-link">
            <Store :size="17" />
            {{ t('marketTitle') }}
          </router-link>
          <router-link v-if="auth.user" to="/publish" class="nav-link">
            <PackagePlus :size="17" />
            {{ t('publishPlugin') }}
          </router-link>
          <router-link v-if="auth.user" to="/dashboard/plugins" class="nav-link">
            <Boxes :size="17" />
            {{ t('myPlugins') }}
          </router-link>
        </nav>

        <div class="header-actions">
          <v-menu v-if="auth.user" location="bottom end" :min-width="0">
            <template #activator="{ props }">
              <v-btn v-bind="props" variant="text" class="account-button" :aria-label="t('accountMenu')">
                <UserAvatar :src="auth.user.avatar_url" :size="24" />
                <span class="desktop-only">{{ auth.user.display_name || auth.user.email }}</span>
              </v-btn>
            </template>
            <v-list density="compact" class="header-menu">
              <v-list-item to="/profile" :title="t('profile')" :prepend-icon="UserRound" />
              <v-list-item to="/settings/accounts" :title="t('accounts')" :prepend-icon="Link2" />
              <v-list-item tag="button" type="button" role="button" :title="t('logout')" :prepend-icon="LogOut" @click="logout" />
            </v-list>
          </v-menu>
          <v-btn v-else to="/login" color="primary" variant="tonal" :aria-label="t('login')">
            <LogIn :size="17" />
            <span class="desktop-only">{{ t('login') }}</span>
          </v-btn>
          <v-menu v-model="menuOpen" location="bottom end" :min-width="0" :close-on-content-click="false">
            <template #activator="{ props }">
              <v-btn v-bind="props" icon variant="text" :aria-label="t('menu')" :title="t('menu')"><Menu :size="21" /></v-btn>
            </template>
            <v-list density="compact" class="header-menu">
              <div class="mobile-nav">
                <v-list-item to="/market" :title="t('marketTitle')" :prepend-icon="Store" @click="menuOpen = false" />
                <v-list-item v-if="auth.user" to="/publish" :title="t('publishPlugin')" :prepend-icon="PackagePlus" @click="menuOpen = false" />
                <v-list-item v-if="auth.user" to="/dashboard/plugins" :title="t('myPlugins')" :prepend-icon="Boxes" @click="menuOpen = false" />
              </div>
              <v-list-item tag="button" type="button" role="button" :prepend-icon="Languages" :title="t('switchLanguage')"
                @click="language = language === 'zh-CN' ? 'en-US' : 'zh-CN'" />
              <v-list-item tag="button" type="button" role="button" :prepend-icon="appearance === 'marketLight' ? Moon : Sun"
                :title="t(appearance === 'marketLight' ? 'dark' : 'light')"
                @click="appearance = appearance === 'marketLight' ? 'marketDark' : 'marketLight'" />
            </v-list>
          </v-menu>
        </div>
      </div>
    </header>

    <v-main>
      <router-view />
    </v-main>
  </v-app>
</template>

<style scoped>
.header-menu {
  --v-list-prepend-gap: 9px;
  padding: 4px 0;
}

.header-menu :deep(.v-list-item) {
  width: 100%;
  padding-inline: 12px;
  text-align: start;
}

.header-menu :deep(.v-list-item__prepend .v-icon) {
  font-size: 17px;
}
</style>

