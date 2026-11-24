import { t } from "./preferences";
import type { OAuthAccount, Plugin, PluginDetail, PublicProfile, Repository, User } from "./types";

interface RequestOptions extends RequestInit {
  retry?: boolean;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(path, {
    signal: AbortSignal.timeout(45000),
    ...options,
    headers,
    credentials: "include",
  });
  if (response.status === 401 && options.retry !== false && path !== "/api/v1/auth/refresh") {
    const refreshed = await fetch("/api/v1/auth/refresh", {
      method: "POST",
      credentials: "include",
      signal: options.signal ?? AbortSignal.timeout(8000),
    });
    if (refreshed.ok) {
      return request<T>(path, { ...options, retry: false });
    }
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = body.detail;
    const errors: Record<string, Parameters<typeof t>[0]> = {
      "Plugin archive exceeds size limit": "packageTooLarge",
      "Avatar exceeds size limit": "avatarTooLarge",
      "Invalid avatar image": "invalidAvatar",
      "Use a PNG, JPEG, or WebP avatar": "invalidAvatar",
      "Invalid email or password": "invalidCredentials",
      "Email is already registered": "emailTaken",
      "Profile not found": "profileMissing",
      "Plugin not found": "pluginMissing",
      "Claim this plugin before publishing": "claimBeforePublish",
      "Some plugins are no longer claimable": "claimConflict",
      "Repository is not claimable by this account": "claimPermission",
      "Repository is not publishable by this account": "publishPermission",
      "Repository already has a market entry": "repositoryAlreadyPublished",
    };
    const version = typeof detail === "string" && detail.match(/^No newer version found; current version is (.+)$/);
    throw new Error(version ? t("noUpdate", { version: version[1] }) :
      typeof detail === "string" ? (Object.hasOwn(errors, detail) ? t(errors[detail]) : detail) :
      Array.isArray(detail) ? t("invalidInput") : t("requestFailed", { status: response.status }));
  }
  return response.json() as Promise<T>;
}

export const api = {
  listPlugins(page: number, pageSize: number, sort: string, search: string, provider: string, signal: AbortSignal) {
    const query = new URLSearchParams({ page: String(page), page_size: String(pageSize), sort });
    if (search) query.set("search", search);
    if (provider) query.set("provider", provider);
    return request<{ items: Plugin[]; total: number }>(`/api/v1/plugins?${query.toString()}`, {
      retry: false,
      signal: AbortSignal.any([signal, AbortSignal.timeout(45000)]),
    });
  },
  getPlugin(id: string) {
    return request<PluginDetail>(`/api/v1/plugins/${encodeURIComponent(id)}`, { retry: false });
  },
  profile(id: string) {
    return request<PublicProfile>(`/api/v1/users/${encodeURIComponent(id)}`, { retry: false });
  },
  editProfile(display_name: string) {
    return request<User>("/api/v1/users/me", { method: "POST", body: JSON.stringify({ display_name }) });
  },
  uploadAvatar(file: File) {
    return request<User>("/api/v1/users/me/avatar", { method: "POST", body: file, headers: { "Content-Type": file.type } });
  },
  removeAvatar() {
    return request<User>("/api/v1/users/me/avatar", { method: "DELETE" });
  },
  me() {
    return request<User>("/api/v1/auth/me", { signal: AbortSignal.timeout(8000) });
  },
  register(payload: { email: string; password: string; display_name: string }) {
    return request<User>("/api/v1/auth/register", {
      method: "POST",
      body: JSON.stringify(payload),
      retry: false,
    });
  },
  login(payload: { email: string; password: string }) {
    return request<User>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify(payload),
      retry: false,
    });
  },
  logout() {
    return request<{ message: string }>("/api/v1/auth/logout", { method: "POST" });
  },
  accounts() {
    return request<OAuthAccount[]>("/api/v1/oauth/accounts");
  },
  connect(provider: string) {
    return request<{ url: string }>(`/api/v1/oauth/${provider}/connect`);
  },
  unlink(provider: string) {
    return request<{ message: string }>(`/api/v1/oauth/${provider}`, { method: "DELETE" });
  },
  repositories(provider: string) {
    return request<Repository[]>(`/api/v1/oauth/${provider}/repositories`);
  },
  publish(provider: string, repositoryId: string) {
    return request<Plugin>("/api/v1/plugins/publish", {
      method: "POST",
      body: JSON.stringify({ provider, repository_id: repositoryId }),
    });
  },
  myPlugins() {
    return request<Plugin[]>("/api/v1/plugins/mine");
  },
  claimablePlugins() {
    return request<Plugin[]>("/api/v1/plugins/claimable");
  },
  claimPlugins(pluginIds: string[]) {
    return request<Plugin[]>("/api/v1/plugins/claim", {
      method: "POST", body: JSON.stringify({ plugin_ids: pluginIds }),
    });
  },
  checkUpdate(pluginId: string) {
    return request<Plugin>(`/api/v1/plugins/${pluginId}/check-update`, { method: "POST" });
  },
  unpublish(pluginId: string) {
    return request<{ message: string }>(`/api/v1/plugins/${pluginId}/unpublish`, { method: "POST" });
  },
};

