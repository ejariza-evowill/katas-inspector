import { copyFile, mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const currentDir = dirname(fileURLToPath(import.meta.url));
const appRoot = resolve(currentDir, "..");
const repoRoot = resolve(appRoot, "..");
const targetDir = resolve(appRoot, "public", "data");

const csvFiles = ["summary.csv", "completed_katas.csv", "kata_scoring_rules.csv"];

await mkdir(targetDir, { recursive: true });

for (const fileName of csvFiles) {
  await copyFile(resolve(repoRoot, fileName), resolve(targetDir, fileName));
  console.log(`Copied ${fileName} to public/data/${fileName}`);
}
