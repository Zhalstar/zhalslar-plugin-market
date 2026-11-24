import { expect, test } from "@playwright/test";

test("publishes selected repositories and retries only failures", async ({ page }, testInfo) => {
  const names = ["plugin-first", "plugin-invalid", "plugin-last", "unrelated"];
  const requests: string[] = [];
  if (testInfo.project.name === "mobile") {
    await page.addInitScript(() => localStorage.setItem("zhalhub-theme", "marketDark"));
  }

  await page.route("**/api/v1/auth/me", (route) => route.fulfill({ json: {
    id: "publisher", display_name: "Publisher", avatar_url: null,
  } }));
  await page.route("**/api/v1/oauth/accounts", (route) => route.fulfill({ json: [
    { provider: "github", username: "publisher" },
    { provider: "gitee", username: "publisher" },
  ] }));
  await page.route("**/api/v1/oauth/github/repositories", (route) => route.fulfill({ json: names.map((id) => ({
    id, provider: "github", full_name: `publisher/${id}`,
  })) }));
  await page.route("**/api/v1/oauth/gitee/repositories", (route) => route.fulfill({ json: [
    { id: "plugin-invalid", provider: "gitee", full_name: "publisher/gitee-plugin" },
  ] }));
  await page.route("**/api/v1/plugins/publish", async (route) => {
    const { provider, repository_id: id } = route.request().postDataJSON();
    requests.push(`${provider}/${id}`);
    if (id === "plugin-invalid" && requests.length === 2) {
      await route.fulfill({ status: 422, json: { detail: "Missing metadata.yaml" } });
    } else {
      await route.fulfill({ status: 201, json: { id } });
    }
  });

  await page.goto("/publish");
  const search = page.getByRole("textbox", { name: "搜索仓库" });
  await expect(search).toBeEnabled();
  const option = page.locator(".repository-option").first();
  await expect(option.locator("svg rect")).toBeVisible();
  await page.getByRole("checkbox", { name: "publisher/unrelated" }).check();
  await expect(page.locator(".selection-toolbar svg.lucide-square-minus")).toBeVisible();
  await search.fill("PLUGIN");
  await page.getByRole("checkbox", { name: "全选搜索结果" }).check();
  await expect(option.locator("svg path")).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("repository-checkboxes.png"), fullPage: true });
  await expect(page.getByText("已选 4 个")).toBeVisible();
  await search.fill("");
  await page.getByRole("checkbox", { name: "publisher/unrelated" }).uncheck();
  await page.getByRole("button", { name: "发布所选（3）" }).click();

  await expect(page.getByRole("heading", { name: "发布完成：成功 2，失败 1" })).toBeVisible();
  await expect(page.getByRole("link", { name: "publisher/plugin-last" })).toHaveAttribute("href", "/plugins/plugin-last");
  await expect(page.getByText("Missing metadata.yaml")).toBeVisible();
  await expect(page.getByRole("checkbox", { name: "publisher/plugin-invalid" })).toBeChecked();
  expect(requests).toEqual(["github/plugin-first", "github/plugin-invalid", "github/plugin-last"]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);

  await page.getByRole("button", { name: "发布所选（1）" }).click();
  await expect(page.getByRole("heading", { name: "发布完成：成功 1，失败 0" })).toBeVisible();
  await expect(page.getByRole("button", { name: "发布所选（0）" })).toBeDisabled();
  expect(requests).toEqual(["github/plugin-first", "github/plugin-invalid", "github/plugin-last", "github/plugin-invalid"]);

  await page.getByRole("checkbox", { name: "publisher/plugin-invalid" }).check();
  await page.getByRole("button", { name: "Gitee" }).click();
  await expect(page.getByRole("checkbox", { name: "publisher/gitee-plugin" })).not.toBeChecked();
  await expect(page.getByRole("button", { name: "发布所选（0）" })).toBeDisabled();
});
