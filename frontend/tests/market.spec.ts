import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/plugins/*/logo", (route) => route.abort());
});

const returningVisitor = test.extend({
  page: async ({ page }, use) => {
    await page.addInitScript(() => localStorage.setItem("zhalhub-market-guide-dismissed", "1"));
    await use(page);
  },
});

test("welcome guide copies the market feed, dismisses, and can reopen", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.goto("/market");
  const guide = page.getByRole("dialog", { name: "欢迎使用 ZhalHub" });
  await expect(guide).toBeVisible();
  await expect(guide).toContainText("添加插件源");
  const source = new URL("/market.json", page.url()).href;
  await expect(guide.locator("code")).toHaveText(source);
  await guide.getByRole("button", { name: "复制地址" }).click();
  await expect(guide.getByRole("button", { name: "已复制" })).toBeVisible();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(source);
  await guide.getByRole("button", { name: "知道了" }).click();
  await expect(guide).toBeHidden();
  await page.reload();
  const trigger = page.getByRole("button", { name: "接入指南" });
  await expect(trigger).toBeVisible();
  await expect(guide).toBeHidden();
  await trigger.click();
  await expect(guide).toBeVisible();
  await expect(guide.getByRole("button", { name: "复制地址" })).toBeVisible();
});

returningVisitor("market renders plugin data without horizontal overflow", async ({ page }, testInfo) => {
  await page.goto("/market");
  await expect(page.getByRole("heading", { name: "插件市场" })).toBeVisible();
  await expect(page.locator(".plugin-card").first()).toBeVisible();
  await expect(page.locator(".plugin-card")).toHaveCount(9);
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
  );
  expect(overflow).toBe(false);
  const logo = page.locator(".plugin-card__logo").first();
  await expect(logo).toHaveCSS("background-color", "rgba(0, 0, 0, 0)");
  await expect(logo).toHaveCSS("border-top-width", "0px");
  await expect(logo).toHaveCSS("border-top-left-radius", "6px");
  await page.screenshot({
    path: testInfo.outputPath("market.png"),
    fullPage: true,
  });
});

returningVisitor("market card footer shows compact metadata only when present", async ({ page }) => {
  await page.route(/\/api\/v1\/plugins\?/, async (route) => {
    const response = await route.fetch();
    const { items: [first, second] } = await response.json();
    await route.fulfill({ json: { total: 2, items: [
      { ...first, author: "Author", stars: 0, version: "1.0.0", astrbot_version: ">=4.11", support_platforms: ["Telegram", "QQ"], tags: ["Tools", "Utility"], logo: "" },
      { ...second, author: "Author", stars: null, version: "", astrbot_version: "", support_platforms: [], tags: [], logo: "" },
    ] } });
  });
  await page.goto("/market");
  const footers = page.locator(".plugin-card__footer");
  await expect(footers.first()).toHaveText(/Author\s*1\.0\.0\s*0\s*>=4\.11\s*Telegram\+1\s*Tools\+1/);
  await expect(footers.first()).not.toContainText(/[:：]|未声明/);
  await expect(footers.nth(1)).toHaveText("Author");
  expect(await footers.first().evaluate((footer) => footer.scrollWidth <= footer.clientWidth)).toBe(true);
});

returningVisitor("market pagination returns to the same page and search resets it", async ({ page }) => {
  await page.goto("/market");
  const cards = page.locator(".plugin-card");
  await expect(cards).toHaveCount(9);
  const first = await cards.first().getByRole("link").getAttribute("href");
  await page.getByRole("button", { name: "下一页" }).click();
  await expect(page).toHaveURL(/page=2/);
  await expect(cards).toHaveCount(9);
  await expect(cards.first().getByRole("link")).not.toHaveAttribute("href", first!);
  await cards.first().click();
  await expect(page.getByRole("tab", { name: "文档" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("tab", { name: "概览" })).toHaveCount(0);
  await page.getByRole("link", { name: "返回市场" }).click();
  await expect(page).toHaveURL(/\/market\?page=2$/);
  await page.getByRole("textbox", { name: "搜索插件" }).fill("astrbot_plugin_afdian");
  await expect(cards).toHaveCount(1);
  await expect(page).not.toHaveURL(/page=2/);
  await expect(page.getByRole("navigation", { name: "插件分页" })).toHaveCount(0);
});

returningVisitor("market offers page size and sorting controls", async ({ page }) => {
  await page.goto("/market?page=2");
  const cards = page.locator(".plugin-card");
  const size = page.getByRole("combobox", { name: "每页" });
  for (const [label, count] of [["18", 18], ["27", 27], ["不限", 46], ["9", 9]] as const) {
    await size.press("ArrowDown");
    await page.getByRole("option", { name: label, exact: true }).click();
    await expect(page).not.toHaveURL(/page=2/);
    await expect(cards).toHaveCount(count);
    if (label === "不限") await expect(page.getByRole("navigation", { name: "插件分页" })).toHaveCount(0);
  }
  await page.getByRole("button", { name: "下一页" }).click();
  await expect(page).toHaveURL(/page=2/);
  await page.getByRole("combobox", { name: "排序" }).press("ArrowDown");
  await page.getByRole("option", { name: "名称升序" }).click();
  await expect(page).toHaveURL(/\/market\?sort=name$/);
  const response = await page.request.get("/api/v1/plugins?sort=name");
  const { items } = await response.json();
  await expect(cards.first().getByRole("link")).toHaveAttribute("href", `/plugins/${items[0].id}?sort=name`);
  await expect(cards).toHaveCount(9);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(await page.evaluate(() => document.documentElement.clientWidth));
  await page.getByRole("combobox", { name: "来源" }).press("ArrowDown");
  await page.getByRole("option", { name: "Gitee" }).click();
  await expect(page).toHaveURL(/provider=gitee/);
  await expect(page.getByText("没有匹配的插件")).toBeVisible();
});

returningVisitor("detail renders safe centered HTML and does not warn when the tab has content", async ({ page }) => {
  await page.route(/\/api\/v1\/plugins\/[^/?]+(?:\?.*)?$/, async (route) => {
    const response = await route.fetch();
    const item = await response.json();
    await route.fulfill({ json: {
      ...item, repo: "https://github.com/example/plugin", provider: "github", sync_state: "failed", docs_ref: "commit",
      author: "Author", version: "1.0.0", stars: 0, astrbot_version: ">=4.11", support_platforms: ["Telegram", "QQ"], tags: ["Tools", "Utility"],
      documents: { readme: { path: "docs/README.md", markdown: '<div align="center"><strong>Centered text</strong><img src="./badge.png" alt="Badge" onerror="void(0)"></div>\n\n[Guide](/GUIDE.md)' } },
    } });
  });
  await page.route("https://raw.githubusercontent.com/example/plugin/**", (route) => route.abort());
  await page.goto("/market");
  await page.locator(".plugin-card").first().click();
  const facts = page.locator(".summary .facts");
  await expect(facts).toHaveText(/Author\s*1\.0\.0\s*0\s*>=4\.11\s*Telegram\+1\s*Tools\+1/);
  expect(await facts.locator(":scope > span").evaluateAll((items) => new Set(items.map((item) => item.getBoundingClientRect().top)).size)).toBe(1);
  const centered = page.locator('.markdown-body div[align="center"]');
  await expect(centered).toHaveText("Centered text");
  await expect(centered).toHaveCSS("text-align", "center");
  const badge = centered.getByRole("img", { name: "Badge" });
  await expect(badge).toHaveAttribute("src", "https://raw.githubusercontent.com/example/plugin/commit/docs/badge.png");
  expect(await badge.getAttribute("onerror")).toBeNull();
  await expect(page.getByRole("link", { name: "Guide" })).toHaveAttribute("href", "https://github.com/example/plugin/blob/commit/GUIDE.md");
  await expect(page.getByText("未能从仓库同步此内容。")).toHaveCount(0);
  await expect(page.getByText("这是仓库当前文档", { exact: false })).toHaveCount(0);
  const content = page.locator(".detail-content");
  const paragraphCenter = await content.evaluate((element) => {
    const box = element.getBoundingClientRect();
    return Math.abs(box.left + box.width / 2 - window.innerWidth / 2);
  });
  expect(paragraphCenter).toBeLessThan(9);
  await page.getByRole("tab", { name: "更新日志" }).click();
  await expect(page.getByText("未能从仓库同步此内容。")).toBeVisible();
});

returningVisitor("each archived release points to its own download", async ({ page }) => {
  const releases = ["2.0.0", "1.0.0"].map((version) => ({
    version, published_at: "2026-01-01T00:00:00Z", commit_sha: "abc12345",
    download_url: `/api/v1/plugins/sample/versions/${version}/download`,
    package_bytes: 128, package_sha256: null,
  }));
  await page.route(/\/api\/v1\/plugins\/[^/?]+$/, async (route) => {
    const response = await route.fetch();
    await route.fulfill({ json: { ...await response.json(), version: "2.0.0", versions: releases } });
  });
  await page.goto("/market");
  await page.locator(".plugin-card").first().click();
  await page.getByRole("tab", { name: "版本" }).click();
  for (const release of releases) {
    const row = page.locator(".version-row").filter({ hasText: release.version });
    await expect(row.getByRole("link", { name: "下载 ZIP" })).toHaveAttribute("href", release.download_url);
  }
});

returningVisitor("my profile edits personal information and keeps hosting accounts separate", async ({ page }, testInfo) => {
  const email = `owner-${Date.now()}-${Math.random().toString(16).slice(2)}@example.com`;
  await page.goto("/register");
  await page.getByLabel("显示名称").fill("测试发布者");
  await page.getByLabel("邮箱").fill(email);
  await page.getByLabel("密码").fill("market-password-42");
  await page.getByRole("button", { name: "注册", exact: true }).last().click();
  await expect(page).toHaveURL(/\/market$/);
  await page.getByRole("button", { name: "账号菜单" }).click();
  const accountMenu = page.locator(".v-overlay--active .header-menu");
  await expect(accountMenu.locator(".v-list-item__prepend svg")).toHaveCount(3);
  expect((await accountMenu.boundingBox())!.width).toBeLessThan(150);
  await accountMenu.getByText("我的主页", { exact: true }).click();
  await expect(page).toHaveURL(/\/profile$/);
  await expect(page.getByRole("heading", { name: "个人资料" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "托管账号" })).toHaveCount(0);
  await expect(page.getByText(email, { exact: true }).last()).toBeVisible();
  await expect(page.locator(".plugin-card")).toHaveCount(0);
  await page.goto("/settings/accounts?linked=github");
  await expect(page).toHaveURL(/\/settings\/accounts\?linked=github$/);
  await expect(page.getByRole("heading", { name: "托管账号" })).toBeVisible();
  await page.goto("/profile");
  await page.locator('input[type="file"]').setInputFiles({
    name: "avatar.png", mimeType: "image/png",
    buffer: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aF1cAAAAASUVORK5CYII=", "base64"),
  });
  const settingsAvatar = page.locator(".avatar-actions .user-avatar img");
  await expect(settingsAvatar).toHaveJSProperty("naturalWidth", 1);
  const avatarUrl = await settingsAvatar.getAttribute("src");
  await page.getByLabel("显示名称").fill("新版发布者");
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await expect(page.getByText("资料已保存")).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("显示名称")).toHaveValue("新版发布者");
  await expect(settingsAvatar).toHaveJSProperty("naturalWidth", 1);
  await page.screenshot({ path: testInfo.outputPath("profile.png"), fullPage: true });
  await page.route(/\/api\/v1\/plugins\?/, async (route) => {
    const response = await route.fetch();
    const listing = await response.json();
    listing.items[0].publisher_avatar_url = avatarUrl;
    await route.fulfill({ json: listing });
  });
  await page.goto("/market");
  await expect(page.locator(".plugin-card").first().locator(".user-avatar img")).toHaveJSProperty("naturalWidth", 1);
});

returningVisitor("my plugins can claim and manage entries on shared cards", async ({ page }, testInfo) => {
  const candidates = [
    { id: "one", display_name: "First plugin", name: "plugin_one", repo: "https://github.com/example/one", version: "1.0.0", status: "published", provider: "github" },
    { id: "two", display_name: "Second plugin", name: "plugin_two", repo: "https://github.com/example/two", version: "1.0.0", status: "published", provider: "github" },
  ].map((item) => ({ ...item, author: "Owner", desc: "A sample plugin", support_platforms: [], tags: [] }));
  let mine: typeof candidates = [];
  await page.route("**/api/v1/auth/me", (route) => route.fulfill({ json: { id: "owner", display_name: "Owner" } }));
  await page.route("**/api/v1/plugins/mine", (route) => route.fulfill({ json: mine }));
  await page.route("**/api/v1/plugins/claimable", (route) => route.fulfill({ json: candidates }));
  await page.route("**/api/v1/plugins/claim", (route) => {
    expect(route.request().postDataJSON()).toEqual({ plugin_ids: ["one"] });
    mine = candidates.slice(0, 1);
    return route.fulfill({ json: mine });
  });
  await page.route("**/api/v1/plugins/one/check-update", (route) => {
    mine[0] = { ...mine[0], version: "2.0.0" };
    return route.fulfill({ json: mine[0] });
  });
  await page.route("**/api/v1/plugins/one/unpublish", (route) => {
    mine[0] = { ...mine[0], status: "unpublished" };
    return route.fulfill({ json: { message: "Plugin unpublished" } });
  });
  await page.goto("/dashboard/plugins");
  await page.getByRole("button", { name: "认领插件" }).click();
  const dialog = page.getByRole("dialog", { name: "认领插件" });
  await expect(dialog.getByRole("button", { name: "认领 0 项" })).toBeDisabled();
  await dialog.getByRole("checkbox", { name: "全选" }).check();
  await expect(dialog.getByRole("button", { name: "认领 2 项" })).toBeEnabled();
  await dialog.getByRole("checkbox", { name: /Second plugin/ }).uncheck();
  await dialog.getByRole("button", { name: "认领 1 项" }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByText("已认领 1 个插件。")).toBeVisible();
  const card = page.locator(".plugin-card");
  await expect(card.getByRole("heading", { name: "First plugin" })).toBeVisible();
  await expect(card.getByRole("link")).toHaveAttribute("href", "/plugins/one");
  await expect(card.locator("a button")).toHaveCount(0);
  await card.getByRole("button", { name: "检测更新" }).click();
  await expect(card.getByText("2.0.0", { exact: true })).toBeVisible();
  await expect(page).toHaveURL(/\/dashboard\/plugins$/);
  await page.screenshot({ path: testInfo.outputPath("my-plugins.png"), fullPage: true });
  await card.getByRole("button", { name: "下架", exact: true }).click();
  await expect(card.getByText("已下架")).toBeVisible();
  await expect(card.getByRole("link", { name: "重新发布" })).toHaveAttribute("href", "/publish");
  await expect(card.getByRole("link")).toHaveCount(1);
});

returningVisitor("preferences persist and the detail tabs work", async ({ page }) => {
  await page.goto("/market");
  await page.getByRole("button", { name: "菜单", exact: true }).click();
  await page.getByRole("button", { name: "切换英文", exact: true }).click();
  await expect(page.getByRole("button", { name: "切换中文", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Dark mode", exact: true }).click();
  await expect(page.getByRole("button", { name: "Light mode", exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { name: "Plugin market" })).toBeVisible();
  await expect(page.locator(".v-application")).toHaveClass(/marketDark/);
  await page.locator(".plugin-card").first().click();
  const logo = page.locator(".summary__logo");
  await expect(logo).toHaveCSS("background-color", "rgba(0, 0, 0, 0)");
  await expect(logo).toHaveCSS("border-top-width", "0px");
  await page.getByRole("tab", { name: "Documentation" }).click();
  await expect(page.getByText("Repository documents have not been synced yet.")).toBeVisible();
  await page.getByRole("tab", { name: "Versions" }).click();
  await expect(page.getByText("No archived package")).toBeVisible();
  await expect(page.getByRole("button", { name: "Download ZIP" })).toBeDisabled();
});
