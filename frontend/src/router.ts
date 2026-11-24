import { createRouter, createWebHistory } from "vue-router";
import { useAuthStore } from "./stores/auth";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", redirect: "/market" },
    { path: "/market", component: () => import("./views/MarketPage.vue") },
    { path: "/plugins/:id", component: () => import("./views/PluginDetailPage.vue") },
    { path: "/users/:id", name: "public-profile", component: () => import("./views/UserProfilePage.vue") },
    { path: "/profile", component: () => import("./views/MyProfilePage.vue"), meta: { requiresAuth: true } },
    { path: "/settings/profile", redirect: "/profile" },
    { path: "/settings/accounts", component: () => import("./views/AccountsPage.vue"), meta: { requiresAuth: true } },
    { path: "/login", component: () => import("./views/AuthPage.vue") },
    {
      path: "/register",
      component: () => import("./views/AuthPage.vue"),
      props: { initialMode: "register" },
    },
    {
      path: "/publish",
      component: () => import("./views/PublishPage.vue"),
      meta: { requiresAuth: true },
    },
    {
      path: "/dashboard/plugins",
      component: () => import("./views/DashboardPage.vue"),
      meta: { requiresAuth: true },
    },
  ],
  scrollBehavior: () => ({ top: 0 }),
});

router.beforeEach(async (to) => {
  const auth = useAuthStore();
  const authPage = to.path === "/login" || to.path === "/register";
  if (!auth.initialized && (to.meta.requiresAuth || authPage || to.name === "public-profile")) await auth.initialize();
  if (to.name === "public-profile" && auth.user?.id === to.params.id) return "/profile";
  if (to.meta.requiresAuth && !auth.user) {
    return { path: "/login", query: { next: to.fullPath } };
  }
  if (authPage && auth.user) {
    return "/market";
  }
});

export default router;

