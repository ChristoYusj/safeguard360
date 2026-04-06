const http = require("http");
const fs = require("fs");
const path = require("path");
const { parse } = require("@babel/parser");
const traverse = require("@babel/traverse").default;
const generate = require("@babel/generator").default;
const { transform } = require("sucrase");

const rootDir = path.resolve(__dirname, "..");
const host = process.env.HOST || "127.0.0.1";
const port = Number(process.env.PORT || 5173);

const importMap = {
  imports: {
    react: "https://esm.sh/react@18.2.0?dev",
    "react/jsx-runtime": "https://esm.sh/react@18.2.0/jsx-runtime?dev",
    "react/jsx-dev-runtime":
      "https://esm.sh/react@18.2.0/jsx-dev-runtime?dev",
    "react-dom/client": "https://esm.sh/react-dom@18.2.0/client?dev",
    "react-router-dom": "https://esm.sh/react-router-dom@6.21.0?dev",
    "framer-motion": "https://esm.sh/framer-motion@12.38.0?dev",
  },
};

function send(res, statusCode, body, contentType) {
  res.writeHead(statusCode, {
    "Content-Type": contentType,
    "Cache-Control": "no-store",
  });
  res.end(body);
}

function toWebPath(filePath) {
  return `/${path.relative(rootDir, filePath).split(path.sep).join("/")}`;
}

function resolveFilePath(requestPath) {
  const normalized = path.normalize(requestPath).replace(/^(\.\.[/\\])+/, "");
  const absolutePath = path.join(rootDir, normalized);
  if (!absolutePath.startsWith(rootDir)) {
    return null;
  }
  return absolutePath;
}

function resolveImportPath(importerPath, specifier) {
  const basePath = path.resolve(path.dirname(importerPath), specifier);
  const directCandidate = basePath;

  if (fs.existsSync(directCandidate) && fs.statSync(directCandidate).isFile()) {
    return directCandidate;
  }

  const extensions = [".js", ".jsx", ".css"];
  for (const extension of extensions) {
    const candidate = `${basePath}${extension}`;
    if (fs.existsSync(candidate) && fs.statSync(candidate).isFile()) {
      return candidate;
    }
  }

  for (const extension of [".js", ".jsx"]) {
    const candidate = path.join(basePath, `index${extension}`);
    if (fs.existsSync(candidate) && fs.statSync(candidate).isFile()) {
      return candidate;
    }
  }

  throw new Error(
    `Unable to resolve "${specifier}" from ${path.relative(rootDir, importerPath)}`,
  );
}

function rewriteModuleImports(code, importerPath) {
  const ast = parse(code, {
    sourceType: "module",
  });

  const rewriteSource = (node) => {
    if (!node || !node.value || !node.value.startsWith(".")) {
      return;
    }

    const resolved = resolveImportPath(importerPath, node.value);
    const webPath = toWebPath(resolved);

    if (webPath.endsWith(".css")) {
      node.value = `/@style?path=${encodeURIComponent(webPath)}`;
      return;
    }

    node.value = webPath;
  };

  traverse(ast, {
    ImportDeclaration(pathRef) {
      rewriteSource(pathRef.node.source);
    },
    ExportAllDeclaration(pathRef) {
      rewriteSource(pathRef.node.source);
    },
    ExportNamedDeclaration(pathRef) {
      rewriteSource(pathRef.node.source);
    },
  });

  return generate(ast, { comments: true }).code;
}

function transformModule(filePath) {
  const source = fs.readFileSync(filePath, "utf8");
  const transformed = transform(source, {
    transforms: ["jsx"],
    jsxRuntime: "automatic",
    production: false,
    filePath,
  }).code;

  return rewriteModuleImports(transformed, filePath);
}

function serveIndexHtml(res) {
  const indexPath = path.join(rootDir, "index.html");
  let html = fs.readFileSync(indexPath, "utf8");
  const mapTag = `<script type="importmap">${JSON.stringify(importMap, null, 2)}</script>`;
  html = html.replace("</head>", `  ${mapTag}\n  </head>`);
  send(res, 200, html, "text/html; charset=utf-8");
}

function serveStyleModule(res, reqUrl) {
  const cssPath = reqUrl.searchParams.get("path");
  const styleId = `style-${Buffer.from(cssPath || "").toString("base64url")}`;

  if (!cssPath) {
    send(res, 400, "Missing style path.", "text/plain; charset=utf-8");
    return;
  }

  const body = `const id = ${JSON.stringify(styleId)};
if (!document.getElementById(id)) {
  const link = document.createElement("link");
  link.id = id;
  link.rel = "stylesheet";
  link.href = ${JSON.stringify(cssPath)};
  document.head.appendChild(link);
}
export default ${JSON.stringify(cssPath)};
`;

  send(res, 200, body, "application/javascript; charset=utf-8");
}

function serveAsset(res, filePath, contentType) {
  if (!fs.existsSync(filePath) || !fs.statSync(filePath).isFile()) {
    send(res, 404, "Not found.", "text/plain; charset=utf-8");
    return;
  }

  send(res, 200, fs.readFileSync(filePath), contentType);
}

const server = http.createServer((req, res) => {
  try {
    const reqUrl = new URL(req.url || "/", `http://${req.headers.host}`);
    const pathname = decodeURIComponent(reqUrl.pathname);

    if (pathname === "/@style") {
      serveStyleModule(res, reqUrl);
      return;
    }

    if (
      pathname === "/" ||
      (!path.extname(pathname) && !pathname.startsWith("/src/"))
    ) {
      serveIndexHtml(res);
      return;
    }

    const filePath = resolveFilePath(pathname.slice(1));
    if (!filePath) {
      send(res, 403, "Forbidden.", "text/plain; charset=utf-8");
      return;
    }

    if (pathname.endsWith(".css")) {
      serveAsset(res, filePath, "text/css; charset=utf-8");
      return;
    }

    if (pathname.endsWith(".js") || pathname.endsWith(".jsx")) {
      const body = transformModule(filePath);
      send(res, 200, body, "application/javascript; charset=utf-8");
      return;
    }

    if (pathname.endsWith(".svg")) {
      serveAsset(res, filePath, "image/svg+xml");
      return;
    }

    send(res, 404, "Not found.", "text/plain; charset=utf-8");
  } catch (error) {
    console.error("[dev-fallback]", error);
    send(
      res,
      500,
      `Fallback dev server error:\n${error.stack || error.message}`,
      "text/plain; charset=utf-8",
    );
  }
});

server.listen(port, host, () => {
  console.log(`Fallback dev server ready at http://${host}:${port}/`);
});
