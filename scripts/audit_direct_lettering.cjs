#!/usr/bin/env node
"use strict";

const fs = require("fs");
const os = require("os");
const path = require("path");

function loadSharp() {
  const candidates = [
    process.env.COMIC_SHARP_PATH,
    "sharp",
    path.join(os.homedir(), ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/sharp"),
  ].filter(Boolean);
  const failures = [];
  for (const candidate of candidates) {
    try {
      return require(candidate);
    } catch (error) {
      failures.push(`${candidate}: ${error.code || error.message}`);
    }
  }
  throw new Error(`Cannot load sharp. Set COMIC_SHARP_PATH. Tried:\n${failures.join("\n")}`);
}

const sharp = loadSharp();

function parseArgs(argv) {
  const result = {};
  for (let index = 0; index < argv.length; index += 1) {
    const key = argv[index];
    if (["--root", "--source-root", "--layout"].includes(key)) result[key.slice(2)] = argv[++index];
  }
  if (!result.root || !result.layout) {
    throw new Error("Usage: audit_direct_lettering.cjs --root DIRECT_DIR --layout comic-layout.json [--source-root SOURCE_DIR]");
  }
  result.root = path.resolve(result.root);
  result.layout = path.resolve(result.layout);
  result.sourceRoot = path.resolve(result.sourceRoot || result.root);
  return result;
}

const args = parseArgs(process.argv.slice(2));
const layout = JSON.parse(fs.readFileSync(args.layout, "utf8"));
const W = Number(layout.width);
const H = Number(layout.height);
if (!Number.isInteger(W) || W < 1 || !Number.isInteger(H) || H < 1) {
  throw new Error("comic-layout.json must define positive integer width and height");
}
const SCALE = Math.min(W, H) / 1000;
const preview = layout.preview || {};
const PREVIEW_W = Number.isInteger(preview.width) && preview.width > 0
  ? preview.width
  : Math.min(W, 320);
const PREVIEW_H = Number.isInteger(preview.height) && preview.height > 0
  ? preview.height
  : Math.max(1, Math.round(H * PREVIEW_W / W));
const auditOptions = layout.direct_lettering_audit || {};
const OPTIONS = {
  sourceDarkLuma: auditOptions.source_dark_luma || 150,
  sourceLightLuma: auditOptions.source_light_luma || 170,
  finalInkLuma: auditOptions.final_ink_luma || 105,
  minimumDarkening: auditOptions.minimum_darkening || 65,
  sourceDarkExclusionRadius: auditOptions.source_dark_exclusion_radius || 4,
  searchPadding: auditOptions.search_padding || 24,
  maximumOutsideInsetRatio: auditOptions.maximum_outside_inset_ratio || 0.02,
  minimumInkPixels: auditOptions.minimum_ink_pixels || Math.max(20, Math.round(80 * SCALE * SCALE)),
  centerRatio: auditOptions.center_ratio || 0.08,
  minimumCenterTolerance: auditOptions.minimum_center_tolerance || Math.max(3, Math.round(12 * SCALE)),
};

const xml = (value) => String(value)
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;");

const luma = (data, index) => (
  0.2126 * data[index] + 0.7152 * data[index + 1] + 0.0722 * data[index + 2]
);

function buildDarkIntegral(source) {
  const integral = new Uint32Array((W + 1) * (H + 1));
  for (let y = 0; y < H; y += 1) {
    let rowSum = 0;
    for (let x = 0; x < W; x += 1) {
      rowSum += luma(source, (y * W + x) * 3) < OPTIONS.sourceDarkLuma ? 1 : 0;
      integral[(y + 1) * (W + 1) + x + 1] = integral[y * (W + 1) + x + 1] + rowSum;
    }
  }
  return integral;
}

function hasSourceDarkNearby(integral, x, y) {
  const radius = OPTIONS.sourceDarkExclusionRadius;
  const x0 = Math.max(0, x - radius);
  const y0 = Math.max(0, y - radius);
  const x1 = Math.min(W - 1, x + radius);
  const y1 = Math.min(H - 1, y + radius);
  const stride = W + 1;
  const total = integral[(y1 + 1) * stride + x1 + 1]
    - integral[y0 * stride + x1 + 1]
    - integral[(y1 + 1) * stride + x0]
    + integral[y0 * stride + x0];
  return total > 0;
}

function pointInsideRect([x, y, width, height], px, py, inset = 0) {
  return px >= x + inset && px <= x + width - inset
    && py >= y + inset && py <= y + height - inset;
}

function pointInsideEllipse([x, y, width, height], px, py, inset = 0) {
  const radiusX = width / 2 - inset;
  const radiusY = height / 2 - inset;
  if (radiusX <= 0 || radiusY <= 0) return false;
  const centerX = x + width / 2;
  const centerY = y + height / 2;
  return ((px - centerX) / radiusX) ** 2 + ((py - centerY) / radiusY) ** 2 <= 1;
}

function detectNewInk(source, finalImage, integral, item, boundsKey, shape) {
  const outer = item[boundsKey];
  const [x, y, width, height] = outer;
  const padding = OPTIONS.searchPadding;
  const startX = Math.max(0, Math.floor(x - padding));
  const startY = Math.max(0, Math.floor(y - padding));
  const endX = Math.min(W, Math.ceil(x + width + padding));
  const endY = Math.min(H, Math.ceil(y + height + padding));
  const inset = item.min_clearance || (boundsKey === "bubble"
    ? Math.max(3, Math.round(12 * SCALE))
    : Math.max(1, Math.round(3 * SCALE)));
  let count = 0;
  let outsideBody = 0;
  let outsideInset = 0;
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;

  for (let py = startY; py < endY; py += 1) {
    for (let px = startX; px < endX; px += 1) {
      const index = (py * W + px) * 3;
      const sourceLuma = luma(source, index);
      const finalLuma = luma(finalImage, index);
      const isNewInk = sourceLuma > OPTIONS.sourceLightLuma
        && finalLuma < OPTIONS.finalInkLuma
        && sourceLuma - finalLuma > OPTIONS.minimumDarkening
        && !hasSourceDarkNearby(integral, px, py);
      if (!isNewInk) continue;
      count += 1;
      minX = Math.min(minX, px);
      minY = Math.min(minY, py);
      maxX = Math.max(maxX, px);
      maxY = Math.max(maxY, py);
      if (!pointInsideRect(outer, px, py)) outsideBody += 1;
      const inInset = shape === "ellipse"
        ? pointInsideEllipse(outer, px, py, inset)
        : pointInsideRect(outer, px, py, inset);
      if (!inInset) outsideInset += 1;
    }
  }

  if (count === 0) {
    return {
      inkPixels: 0,
      textBounds: null,
      outsideBodyInkPixels: 0,
      outsideInsetInkRatio: null,
      centerOffsetX: null,
      centerOffsetY: null,
    };
  }
  const textBounds = [minX, minY, maxX - minX + 1, maxY - minY + 1];
  const textCenterX = minX + (maxX - minX) / 2;
  const textCenterY = minY + (maxY - minY) / 2;
  const bodyCenterX = x + width / 2;
  const bodyCenterY = y + height / 2;
  return {
    inkPixels: count,
    textBounds,
    outsideBodyInkPixels: outsideBody,
    outsideInsetInkRatio: outsideInset / count,
    centerOffsetX: Math.abs(textCenterX - bodyCenterX),
    centerOffsetY: Math.abs(textCenterY - bodyCenterY),
  };
}

function evaluateBalloon(item, metrics) {
  const [, , width, height] = item.bubble;
  const reasons = [];
  if (metrics.inkPixels < OPTIONS.minimumInkPixels) reasons.push("no reliable new text ink detected");
  if (metrics.outsideBodyInkPixels > 0) reasons.push("new dark ink crosses the measured balloon body");
  if (metrics.outsideInsetInkRatio > OPTIONS.maximumOutsideInsetRatio) {
    reasons.push("too much new ink crosses the inset balloon shape");
  }
  if (metrics.centerOffsetX > Math.max(OPTIONS.minimumCenterTolerance, width * OPTIONS.centerRatio)
    || metrics.centerOffsetY > Math.max(OPTIONS.minimumCenterTolerance, height * OPTIONS.centerRatio)) {
    reasons.push("new text ink is visually off-center");
  }
  return reasons;
}

function evaluateFramedText(metrics) {
  const reasons = [];
  if (metrics.inkPixels < OPTIONS.minimumInkPixels) reasons.push("no reliable new text ink detected");
  if (metrics.outsideBodyInkPixels > 0) reasons.push("new dark ink crosses the measured frame");
  return reasons;
}

async function loadRgb(file, requireExactSize) {
  const metadata = await sharp(file).metadata();
  if (requireExactSize && (metadata.width !== W || metadata.height !== H)) {
    throw new Error(`${file}: ${metadata.width}x${metadata.height}, expected ${W}x${H}`);
  }
  return sharp(file).resize(W, H, { fit: "fill" }).removeAlpha().raw().toBuffer();
}

async function labeledTile(file, label, bounds) {
  const [x, y, width, height] = bounds;
  const padding = 18;
  const left = Math.max(0, Math.floor(x - padding));
  const top = Math.max(0, Math.floor(y - padding));
  const extractWidth = Math.min(W - left, Math.ceil(width + padding * 2));
  const extractHeight = Math.min(H - top, Math.ceil(height + padding * 2));
  const tileWidth = 250;
  const tileHeight = 170;
  const labelHeight = 30;
  const crop = await sharp(file)
    .extract({ left, top, width: extractWidth, height: extractHeight })
    .resize(tileWidth, tileHeight, { fit: "contain", background: "#d7d3cb" })
    .jpeg({ quality: 94 })
    .toBuffer();
  const bar = Buffer.from(`<svg width="${tileWidth}" height="${labelHeight}" xmlns="http://www.w3.org/2000/svg"><rect width="100%" height="100%" fill="#2a2927"/><text x="10" y="21" font-family="sans-serif" font-size="15" font-weight="600" fill="#fff">${xml(label)}</text></svg>`);
  return sharp({ create: { width: tileWidth, height: tileHeight + labelHeight, channels: 3, background: "#fff" } })
    .composite([{ input: bar, left: 0, top: 0 }, { input: crop, left: 0, top: labelHeight }])
    .jpeg({ quality: 94 })
    .toBuffer();
}

async function writeContactSheet(collection, filename, boundsKey) {
  const qa = path.join(args.root, "qa");
  const tileWidth = 250;
  const tileHeight = 200;
  const gap = 14;
  const columns = 4;
  const rows = Math.max(1, Math.ceil(collection.length / columns));
  const composites = [];
  for (let index = 0; index < collection.length; index += 1) {
    const item = collection[index];
    const match = item.id.match(/^P(\d+)-/);
    if (!match) throw new Error(`${item.id}: id must start with P<number>-`);
    const page = match[1].padStart(2, "0");
    const tile = await labeledTile(
      path.join(args.root, `page-${page}.png`),
      `${item.id} · ${item.status}`,
      item[boundsKey],
    );
    composites.push({
      input: tile,
      left: gap + (index % columns) * (tileWidth + gap),
      top: gap + Math.floor(index / columns) * (tileHeight + gap),
    });
  }
  await sharp({
    create: {
      width: columns * tileWidth + (columns + 1) * gap,
      height: rows * tileHeight + (rows + 1) * gap,
      channels: 3,
      background: "#d7d3cb",
    },
  }).composite(composites).jpeg({ quality: 94 }).toFile(path.join(qa, filename));
}

async function writeReviewContact() {
  const qa = path.join(args.root, "qa");
  const previews = path.join(qa, "review-preview-pages");
  fs.mkdirSync(previews, { recursive: true });
  const tileWidth = PREVIEW_W;
  const tileHeight = PREVIEW_H;
  const labelHeight = 30;
  const gap = 18;
  const columns = 3;
  const rows = Math.ceil(layout.pages.length / columns);
  const composites = [];
  for (let index = 0; index < layout.pages.length; index += 1) {
    const page = layout.pages[index];
    const file = path.join(args.root, `page-${page.number}.png`);
    const preview = await sharp(file).resize(tileWidth, tileHeight, { fit: "fill" }).jpeg({ quality: 94 }).toBuffer();
    await sharp(preview).toFile(path.join(previews, `page-${page.number}.jpg`));
    const bar = Buffer.from(`<svg width="${tileWidth}" height="${labelHeight}" xmlns="http://www.w3.org/2000/svg"><rect width="100%" height="100%" fill="#2a2927"/><text x="10" y="21" font-family="sans-serif" font-size="16" font-weight="600" fill="#fff">DIRECT LETTERING · P${Number(page.number)}</text></svg>`);
    const tile = await sharp({ create: { width: tileWidth, height: tileHeight + labelHeight, channels: 3, background: "#fff" } })
      .composite([{ input: bar, left: 0, top: 0 }, { input: preview, left: 0, top: labelHeight }])
      .jpeg({ quality: 94 })
      .toBuffer();
    composites.push({
      input: tile,
      left: gap + (index % columns) * (tileWidth + gap),
      top: gap + Math.floor(index / columns) * (tileHeight + labelHeight + gap),
    });
  }
  await sharp({
    create: {
      width: columns * tileWidth + (columns + 1) * gap,
      height: rows * (tileHeight + labelHeight) + (rows + 1) * gap,
      channels: 3,
      background: "#d7d3cb",
    },
  }).composite(composites).jpeg({ quality: 94 }).toFile(path.join(qa, "review-contact-sheet.jpg"));
}

function writeAudit(name, expected, collection, key) {
  const qa = path.join(args.root, "qa");
  const result = collection.every((item) => item.status === "PASS") && collection.length === expected ? "PASS" : "FAIL";
  fs.writeFileSync(
    path.join(qa, `${name}.json`),
    `${JSON.stringify({ mode: "direct-lettering", expected, audited: collection.length, result, thresholds: OPTIONS, [key]: collection }, null, 2)}\n`,
  );
  const rows = collection.map((item) => `| ${item.id} | ${item.inkPixels} | ${item.centerOffsetX ?? "-"} | ${item.centerOffsetY ?? "-"} | ${item.status} |`);
  fs.writeFileSync(
    path.join(qa, `${name}.md`),
    [`# ${name}`, "", "- 模式：直接排字像素差分审计", `- 审查数量：${collection.length}/${expected}`, `- 结果：${result}`, "", "| ID | 新增墨迹像素 | 横向偏差 | 纵向偏差 | 结果 |", "|---|---:|---:|---:|---|", ...rows, ""].join("\n"),
  );
  return result;
}

async function main() {
  const qa = path.join(args.root, "qa");
  fs.mkdirSync(qa, { recursive: true });
  const balloons = [];
  const framedTexts = [];
  for (const page of layout.pages) {
    const sourceFile = path.join(args.sourceRoot, page.source);
    const finalFile = path.join(args.root, `page-${page.number}.png`);
    if (!fs.existsSync(sourceFile)) throw new Error(`Missing source image: ${sourceFile}`);
    if (!fs.existsSync(finalFile)) throw new Error(`Missing direct-lettering page: ${finalFile}`);
    const source = await loadRgb(sourceFile, false);
    const finalImage = await loadRgb(finalFile, true);
    const integral = buildDarkIntegral(source);

    for (const item of page.balloons || []) {
      const shape = item.shape || "ellipse";
      if (!["ellipse", "rect"].includes(shape)) throw new Error(`${item.id}: unsupported shape ${shape}`);
      const metrics = detectNewInk(source, finalImage, integral, item, "bubble", shape);
      const reasons = evaluateBalloon(item, metrics);
      balloons.push({
        id: item.id,
        text: (item.lines || []).join(" / "),
        bubble: item.bubble,
        shape,
        safeBox: item.box,
        textBounds: metrics.textBounds,
        inkPixels: metrics.inkPixels,
        outsideBodyInkPixels: metrics.outsideBodyInkPixels,
        outsideInsetInkRatio: metrics.outsideInsetInkRatio === null ? null : Number(metrics.outsideInsetInkRatio.toFixed(4)),
        centerOffsetX: metrics.centerOffsetX === null ? null : Number(metrics.centerOffsetX.toFixed(1)),
        centerOffsetY: metrics.centerOffsetY === null ? null : Number(metrics.centerOffsetY.toFixed(1)),
        failureReasons: reasons,
        status: reasons.length === 0 ? "PASS" : "FAIL",
      });
    }

    for (const item of page.framed_text || []) {
      const metrics = detectNewInk(source, finalImage, integral, item, "frame", "rect");
      const reasons = evaluateFramedText(metrics);
      framedTexts.push({
        id: item.id,
        text: (item.lines || []).join(" / "),
        frame: item.frame,
        safeBox: item.box,
        textBounds: metrics.textBounds,
        inkPixels: metrics.inkPixels,
        outsideBodyInkPixels: metrics.outsideBodyInkPixels,
        centerOffsetX: metrics.centerOffsetX === null ? null : Number(metrics.centerOffsetX.toFixed(1)),
        centerOffsetY: metrics.centerOffsetY === null ? null : Number(metrics.centerOffsetY.toFixed(1)),
        failureReasons: reasons,
        status: reasons.length === 0 ? "PASS" : "FAIL",
      });
    }
  }

  const expectedBalloons = layout.expected_balloon_count;
  const expectedFramed = layout.expected_framed_text_count;
  const bubbleResult = writeAudit("bubble-layout-audit", expectedBalloons, balloons, "balloons");
  const framedResult = writeAudit("framed-text-layout-audit", expectedFramed, framedTexts, "items");
  await writeContactSheet(balloons, "bubble-contact-sheet.jpg", "bubble");
  await writeContactSheet(framedTexts, "framed-text-contact-sheet.jpg", "frame");
  await writeReviewContact();
  const visualReview = path.join(qa, "visual-review.md");
  if (!fs.existsSync(visualReview)) {
    fs.writeFileSync(
      visualReview,
      "# 视觉审核\n\n状态：NOT_REVIEWED\n\n- 逐字核对：NOT_REVIEWED\n- 气泡联系表：NOT_REVIEWED\n- 原画冻结区对照：NOT_REVIEWED\n- 目标观看尺寸预览：NOT_REVIEWED\n",
    );
  }
  if (bubbleResult !== "PASS" || framedResult !== "PASS") {
    throw new Error(`Direct-lettering audit failed: balloons=${bubbleResult}, framed_text=${framedResult}`);
  }
  console.log(`Direct-lettering PASS: ${balloons.length} balloons, ${framedTexts.length} framed texts.`);
}

main().catch((error) => {
  console.error(error.stack || error.message);
  process.exit(1);
});
