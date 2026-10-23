// Test-only static hosting of the allowlisted package, including Pages _headers/404 behavior.
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { verifyPackage } from "./verify-public-demo.mjs";
export async function servePublicDemo(directory) {
  const { root, headers, files } = await verifyPackage(directory);
  const contents = new Map(
    await Promise.all(files.map(async (file) => ["/" + file, await readFile(resolve(root, file))])),
  );
  const server = createServer((req, res) => {
    for (const [key, value] of Object.entries(headers)) res.setHeader(key, value);
    if (!["GET", "HEAD"].includes(req.method)) {
      res.writeHead(405).end();
      return;
    }
    const pathname = new URL(req.url, "http://localhost").pathname;
    const file = pathname === "/" ? "/index.html" : pathname;
    const content = file === "/_headers" ? undefined : contents.get(file);
    res.setHeader(
      "Content-Type",
      file.endsWith(".json")
        ? "application/json"
        : file.endsWith(".html") || !content
          ? "text/html; charset=utf-8"
          : "text/plain; charset=utf-8",
    );
    res.writeHead(content ? 200 : 404);
    res.end(req.method === "HEAD" ? undefined : content || contents.get("/404.html"));
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  return {
    origin: "http://127.0.0.1:" + server.address().port,
    close: () => new Promise((resolve) => server.close(resolve)),
  };
}
