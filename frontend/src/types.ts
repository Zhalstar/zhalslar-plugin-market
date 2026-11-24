export interface User {
  id: string;
  email: string;
  display_name: string;
  avatar_url: string | null;
  email_verified: boolean;
  is_admin: boolean;
  created_at: string;
}

export interface Plugin {
  id: string;
  market_id: string;
  author: string;
  name: string;
  display_name: string;
  version: string;
  repo: string;
  desc: string;
  short_desc: string;
  logo: string;
  download_url: string;
  provider: "github" | "gitee" | null;
  status: "published" | "unpublished";
  owner_id: string | null;
  publisher_avatar_url: string | null;
  stars: number | null;
  astrbot_version: string;
  support_platforms: string[];
  tags: string[];
  created_at: string;
  updated_at: string;
}

export interface MarkdownDocument {
  path: string;
  markdown: string;
}

export interface PluginDetail extends Plugin {
  publisher_name: string | null;
  docs_ref: string;
  sync_state: "pending" | "ready" | "failed" | "repository";
  documents: Partial<Record<"readme" | "guide" | "changelog", MarkdownDocument>>;
  versions: {
    version: string;
    commit_sha: string;
    published_at: string;
    download_url: string | null;
    package_bytes: number | null;
    package_sha256: string | null;
  }[];
}

export interface PublicProfile {
  id: string;
  display_name: string;
  avatar_url: string | null;
  plugins: Plugin[];
}

export interface OAuthAccount {
  provider: "github" | "gitee";
  username: string;
  created_at: string;
}

export interface Repository {
  provider: "github" | "gitee";
  id: string;
  full_name: string;
  name: string;
  owner: string;
  url: string;
  default_branch: string;
  private: boolean;
  can_push: boolean;
}

