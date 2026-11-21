# 饰乐的插件市场

这是饰乐维护的 AstrBot 自定义插件源。

## 插件源地址

仓库推送到 GitHub 后，在 AstrBot 的“插件市场 -> 插件源管理”中添加：

```text
https://raw.githubusercontent.com/Zhalstar/zhalslar-plugin-market/main/market.json
```

如果已经启用 GitHub Pages，也可以使用：

```text
https://zhalstar.github.io/zhalslar-plugin-market/market.json
```

## 添加插件

在 `market.json` 根对象中增加插件记录。根 key 必须为
`${author}/${name}`，并且 `author`、`name`、`version` 必须与插件包内的
`metadata.yaml` 完全一致。

```json
{
  "$meta": {
    "schema_version": 1,
    "name": "饰乐的插件市场",
    "version": "2026.11.21"
  },
  "饰乐/astrbot_plugin_example": {
    "author": "饰乐",
    "name": "astrbot_plugin_example",
    "display_name": "示例插件",
    "version": "1.0.0",
    "repo": "https://github.com/Zhalstar/astrbot_plugin_example",
    "desc": "示例插件描述",
    "short_desc": "简短描述",
    "astrbot_version": ">=4.16,<5",
    "support_platforms": [
      "aiocqhttp",
      "qq_official"
    ],
    "tags": [
      "示例"
    ]
  }
}
```

每次修改 `market.json` 后运行：

```bash
python scripts/update_md5.py
```

该命令会校验市场数据并更新 `market-md5.json`。提交时应同时提交这两个
JSON 文件；GitHub Actions 会检查它们是否匹配。

也可以从现有 AstrBot 实例批量导入已安装插件的 `metadata.yaml`：

```bash
python scripts/import_plugins.py /path/to/AstrBot/data/plugins
python scripts/update_md5.py
```

导入脚本需要 PyYAML，并会跳过缺少 `name`、`author` 或 `repo` 的插件，
因为这些插件无法形成可安装的市场记录。

## 必填字段

每条插件记录必须包含：

- `author`：作者命名空间。
- `name`：插件内部名称。
- `version`：插件版本。
- `repo`：HTTPS GitHub 仓库地址。
- `desc`：插件描述。

常用可选字段包括 `display_name`、`short_desc`、`download_url`、`logo`、
`tags`、`category`、`support_platforms`、`astrbot_version`、`social_link`、
`updated_at`、`pinned`、`stars` 和 `download_count`。
