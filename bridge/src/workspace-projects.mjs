import fs from "node:fs/promises";
import path from "node:path";

const EXCLUDED = new Set([".git", ".codex", "node_modules"]);

export async function listWorkspaceProjects(workspaceRoot) {
  const entries = await fs.readdir(workspaceRoot, { withFileTypes: true });
  const projects = [];

  for (const entry of entries) {
    if (!entry.isDirectory()) {
      continue;
    }

    if (entry.name.startsWith(".") || EXCLUDED.has(entry.name)) {
      continue;
    }

    projects.push({
      name: entry.name,
      path: path.join(workspaceRoot, entry.name),
    });
  }

  projects.sort((left, right) => left.name.localeCompare(right.name));
  return projects;
}

export async function resolveWorkspaceProject(workspaceRoot, projectName) {
  const projects = await listWorkspaceProjects(workspaceRoot);
  const wanted = projectName.trim().toLowerCase();
  return projects.find((project) => project.name.toLowerCase() === wanted) || null;
}
