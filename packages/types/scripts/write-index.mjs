import { writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const dir = dirname(fileURLToPath(import.meta.url));
const index = `/**
 * types — OpenAPI 生成类型 + 友好别名。
 * 重新生成: npm run generate:types（会刷新 generated.ts；aliases.ts 手写保留）
 */
export type * from './generated';
export type * from './aliases';
`;
writeFileSync(join(dir, "..", "src", "index.ts"), index, "utf8");
console.log("wrote src/index.ts");
