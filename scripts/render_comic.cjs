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
    if (key === "--root" || key === "--layout") result[key.slice(2)] = argv[++index];
  }
  if (!result.root || !result.layout) {
    throw new Error("Usage: render_comic.cjs --root FINAL_DIR --layout comic-layout.json");
  }
  return result;
}

const args = parseArgs(process.argv.slice(2));
const ROOT = path.resolve(args.root);
const layout = JSON.parse(fs.readFileSync(path.resolve(args.layout), "utf8"));
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
const FONT = layout.font_family || "PingFang SC, Hiragino Sans GB, Noto Sans CJK SC, sans-serif";
const balloonAudit = [];
const framedTextAudit = [];

const xml = (value) => String(value)
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;");

function svgText({ x, y, lines, size, gap = 1.18, weight = 600, fill = "#1b1a18", anchor = "middle", transform = "", stroke = "none", strokeWidth = 0 }) {
  const step = size * gap;
  const firstY = y - ((lines.length - 1) * step) / 2;
  const rows = lines.map((line, index) => `<text x="${x}" y="${(firstY + index * step).toFixed(1)}" text-anchor="${anchor}" dominant-baseline="central" alignment-baseline="central" font-family="${xml(FONT)}" font-size="${size}" font-weight="${weight}" fill="${fill}" stroke="${stroke}" stroke-width="${strokeWidth}" paint-order="stroke" stroke-linejoin="round">${xml(line)}</text>`).join("");
  return transform ? `<g transform="${transform}">${rows}</g>` : rows;
}

function assertBoxInside(id, outer, inner, label) {
  const [ox, oy, ow, oh] = outer;
  const [ix, iy, iw, ih] = inner;
  const epsilon = 0.01;
  if (ix < ox - epsilon || iy < oy - epsilon || ix + iw > ox + ow + epsilon || iy + ih > oy + oh + epsilon) {
    throw new Error(`${id}: safe box is outside measured ${label}`);
  }
}

async function renderedTextBounds(markup) {
  const svg = Buffer.from(`<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg">${markup}</svg>`);
  const { info } = await sharp(svg)
    .trim({ background: { r: 0, g: 0, b: 0, alpha: 0 } })
    .png()
    .toBuffer({ resolveWithObject: true });
  if (!Number.isFinite(info.trimOffsetLeft) || !Number.isFinite(info.trimOffsetTop)) {
    throw new Error("Cannot measure rendered text bounds");
  }
  return [-info.trimOffsetLeft, -info.trimOffsetTop, info.width, info.height];
}

function rectContains(outer, inner, epsilon = 0.01) {
  const [ox, oy, ow, oh] = outer;
  const [ix, iy, iw, ih] = inner;
  return ix >= ox - epsilon
    && iy >= oy - epsilon
    && ix + iw <= ox + ow + epsilon
    && iy + ih <= oy + oh + epsilon;
}

function rectClearances(outer, inner) {
  const [ox, oy, ow, oh] = outer;
  const [ix, iy, iw, ih] = inner;
  return [ix - ox, ox + ow - (ix + iw), iy - oy, oy + oh - (iy + ih)];
}

function ellipseContainment(ellipse, inner, clearance) {
  const [x, y, width, height] = ellipse;
  const [ix, iy, iw, ih] = inner;
  const centerX = x + width / 2;
  const centerY = y + height / 2;
  const radiusX = width / 2 - clearance;
  const radiusY = height / 2 - clearance;
  if (radiusX <= 0 || radiusY <= 0) return { fits: false, load: Infinity };
  const corners = [
    [ix, iy],
    [ix + iw, iy],
    [ix, iy + ih],
    [ix + iw, iy + ih],
  ];
  const load = Math.max(...corners.map(([px, py]) => (
    ((px - centerX) / radiusX) ** 2 + ((py - centerY) / radiusY) ** 2
  )));
  return { fits: load <= 1.0001, load };
}

async function balloonText(item) {
  const { id, bubble, box, lines } = item;
  if (!id || !bubble || !box || !Array.isArray(lines) || lines.length === 0) {
    throw new Error("Invalid balloon item");
  }
  if (lines.length > 3) throw new Error(`${id}: balloon text exceeds the 3-line limit`);
  assertBoxInside(id, bubble, box, "balloon body");
  const [x, y, width, height] = box;
  const maxSize = item.max_size || Math.max(10, Math.round(36 * SCALE));
  const minSize = item.min_size || Math.max(8, Math.round(22 * SCALE));
  const gap = item.gap || 1.18;
  const shape = item.shape || "ellipse";
  if (!["ellipse", "rect"].includes(shape)) {
    throw new Error(`${id}: unsupported balloon shape ${shape}; use ellipse or rect`);
  }
  const count = Math.max(...lines.map((line) => Array.from(line).length));
  const initialSize = Math.floor(Math.min(
    maxSize,
    width / Math.max(1, count * 1.06),
    height / Math.max(1, lines.length * 1.22),
  ));
  const [bx, by, bw, bh] = bubble;
  const centerX = x + width / 2;
  const centerY = y + height / 2;
  const minimumRequiredClearance = item.min_clearance || Math.max(3, Math.round(12 * SCALE));
  let accepted = null;
  let lastReason = "unknown fit failure";
  for (let size = initialSize; size >= minSize; size -= 1) {
    const markup = svgText({ x: centerX, y: centerY, lines, size, gap, weight: item.weight || 600, fill: item.fill || "#1b1a18" });
    const textBounds = await renderedTextBounds(markup);
    if (!rectContains(box, textBounds)) {
      lastReason = "rendered glyph bounds exceed the safe box";
      continue;
    }
    const minimumClearance = Math.min(...rectClearances(bubble, textBounds));
    if (minimumClearance < minimumRequiredClearance) {
      lastReason = `rendered glyphs have less than ${minimumRequiredClearance}px outline clearance`;
      continue;
    }
    const ellipse = shape === "ellipse"
      ? ellipseContainment(bubble, textBounds, minimumRequiredClearance)
      : { fits: true, load: null };
    if (!ellipse.fits) {
      lastReason = "rendered glyph corners fall outside the inset ellipse";
      continue;
    }
    const textCenterX = textBounds[0] + textBounds[2] / 2;
    const textCenterY = textBounds[1] + textBounds[3] / 2;
    const offsetX = Math.abs(textCenterX - (bx + bw / 2));
    const offsetY = Math.abs(textCenterY - (by + bh / 2));
    const minimumCenterTolerance = Math.max(3, Math.round(12 * SCALE));
    if (offsetX > Math.max(minimumCenterTolerance, bw * 0.08)
      || offsetY > Math.max(minimumCenterTolerance, bh * 0.08)) {
      lastReason = "rendered glyph bounds are visually off-center";
      continue;
    }
    accepted = { markup, size, textBounds, minimumClearance, ellipseLoad: ellipse.load, offsetX, offsetY };
    break;
  }
  if (!accepted) {
    throw new Error(`${id}: ${lastReason} at the ${minSize}px minimum; rewrite, rewrap, or redraw the ${shape} balloon`);
  }
  balloonAudit.push({
    id,
    text: lines.join(" / "),
    bubble,
    shape,
    safeBox: box,
    textBounds: accepted.textBounds.map((value) => Number(value.toFixed(1))),
    fontSize: accepted.size,
    minimumBubbleClearance: Number(accepted.minimumClearance.toFixed(1)),
    ellipseLoad: accepted.ellipseLoad === null ? null : Number(accepted.ellipseLoad.toFixed(3)),
    centerOffsetX: Number(accepted.offsetX.toFixed(1)),
    centerOffsetY: Number(accepted.offsetY.toFixed(1)),
    status: "PASS",
  });
  return accepted.markup;
}

async function framedText(item) {
  const { id, frame, box, lines, size } = item;
  if (!id || !frame || !box || !Array.isArray(lines) || !size) {
    throw new Error("Invalid framed_text item");
  }
  assertBoxInside(id, frame, box, "frame");
  const [fx, fy, fw, fh] = frame;
  const [x, y, width, height] = box;
  const gap = item.gap || 1.18;
  const anchor = item.anchor || "middle";
  const textX = anchor === "start" ? x : anchor === "end" ? x + width : x + width / 2;
  const textY = y + height / 2;
  const plainMarkup = svgText({
    x: textX,
    y: textY,
    lines,
    size,
    gap,
    weight: item.weight || 600,
    fill: item.fill || "#1b1a18",
    anchor,
  });
  const textBounds = await renderedTextBounds(plainMarkup);
  if (!rectContains(box, textBounds)) {
    throw new Error(`${id}: text exceeds safe box`);
  }
  const clearance = Math.min(...rectClearances(frame, textBounds));
  if (clearance < (item.min_clearance || Math.max(1, Math.round(3 * SCALE)))) {
    throw new Error(`${id}: text too close to frame`);
  }
  const rotation = item.rotation || 0;
  const origin = item.rotation_origin || [fx + fw / 2, fy + fh / 2];
  framedTextAudit.push({
    id,
    text: lines.join(" / "),
    frame,
    safeBox: box,
    textBounds: textBounds.map((value) => Number(value.toFixed(1))),
    fontSize: size,
    rotation,
    minimumFrameClearance: Number(clearance.toFixed(1)),
    status: "PASS",
  });
  return svgText({
    x: textX,
    y: textY,
    lines,
    size,
    gap,
    weight: item.weight || 600,
    fill: item.fill || "#1b1a18",
    anchor,
    transform: rotation ? `rotate(${rotation} ${origin[0]} ${origin[1]})` : "",
  });
}

function signatureText() {
  const item = layout.signature;
  if (!item || !item.text) return "";
  return svgText({
    x: item.x,
    y: item.y,
    lines: [item.text],
    size: item.size || 15,
    weight: item.weight || 500,
    anchor: item.anchor || "end",
    fill: item.fill || "#77736d",
    stroke: item.stroke || "#fffdf7",
    strokeWidth: item.stroke_width || 3,
  });
}

async function makeOverlay(page) {
  const balloons = [];
  for (const item of page.balloons || []) balloons.push(await balloonText(item));
  const framed = [];
  for (const item of page.framed_text || []) framed.push(await framedText(item));
  const body = [
    ...balloons,
    ...framed,
    signatureText(),
  ].join("");
  return Buffer.from(`<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg">${body}</svg>`);
}

async function renderPage(page) {
  const output = path.join(ROOT, `page-${page.number}.png`);
  const overlay = await makeOverlay(page);
  await sharp(path.join(ROOT, page.source))
    .resize(W, H, { fit: "fill" })
    .composite([{ input: overlay }])
    .png()
    .toFile(output);
}

async function labeledTile(file, label, width, height) {
  const image = await sharp(file).resize(width, height, { fit: "fill" }).jpeg({ quality: 94 }).toBuffer();
  const bar = Buffer.from(`<svg width="${width}" height="30" xmlns="http://www.w3.org/2000/svg"><rect width="100%" height="100%" fill="#2a2927"/><text x="10" y="21" font-family="sans-serif" font-size="16" font-weight="600" fill="#fff">${xml(label)}</text></svg>`);
  return sharp({ create: { width, height: height + 30, channels: 3, background: "#fff" } })
    .composite([{ input: bar, left: 0, top: 0 }, { input: image, left: 0, top: 30 }])
    .jpeg({ quality: 94 })
    .toBuffer();
}

async function renderReviewContact() {
  const qa = path.join(ROOT, "qa");
  const previews = path.join(qa, "review-preview-pages");
  fs.mkdirSync(previews, { recursive: true });
  const validPreviews = new Set(layout.pages.map((page) => `page-${page.number}.jpg`));
  for (const file of fs.readdirSync(previews)) {
    if (/^page-\d\d\.jpg$/.test(file) && !validPreviews.has(file)) {
      fs.rmSync(path.join(previews, file));
    }
  }
  const tileW = PREVIEW_W;
  const tileH = PREVIEW_H;
  const gap = 18;
  const columns = 3;
  const rows = Math.ceil(layout.pages.length / columns);
  const composites = [];
  for (let index = 0; index < layout.pages.length; index += 1) {
    const page = layout.pages[index];
    const file = path.join(ROOT, `page-${page.number}.png`);
    const preview = await sharp(file).resize(tileW, tileH, { fit: "fill" }).jpeg({ quality: 94 }).toBuffer();
    await sharp(preview).toFile(path.join(previews, `page-${page.number}.jpg`));
    const tile = await labeledTile(file, `P${Number(page.number)}`, tileW, tileH);
    composites.push({
      input: tile,
      left: gap + (index % columns) * (tileW + gap),
      top: gap + Math.floor(index / columns) * (tileH + 30 + gap),
    });
  }
  await sharp({
    create: {
      width: columns * tileW + (columns + 1) * gap,
      height: rows * (tileH + 30) + (rows + 1) * gap,
      channels: 3,
      background: "#d7d3cb",
    },
  }).composite(composites).jpeg({ quality: 94 }).toFile(path.join(qa, "review-contact-sheet.jpg"));
}

function validateAuditCounts() {
  const balloonIds = balloonAudit.map((item) => item.id);
  const framedIds = framedTextAudit.map((item) => item.id);
  if (new Set(balloonIds).size !== balloonIds.length) throw new Error("Duplicate balloon ids");
  if (new Set(framedIds).size !== framedIds.length) throw new Error("Duplicate framed-text ids");
  if (balloonAudit.length !== layout.expected_balloon_count) {
    throw new Error(`Expected ${layout.expected_balloon_count} balloons, audited ${balloonAudit.length}`);
  }
  if (framedTextAudit.length !== layout.expected_framed_text_count) {
    throw new Error(`Expected ${layout.expected_framed_text_count} framed texts, audited ${framedTextAudit.length}`);
  }
}

function writeAudit(name, expected, collection, key) {
  const qa = path.join(ROOT, "qa");
  fs.mkdirSync(qa, { recursive: true });
  fs.writeFileSync(
    path.join(qa, `${name}.json`),
    `${JSON.stringify({ expected, audited: collection.length, result: "PASS", [key]: collection }, null, 2)}\n`,
  );
  const rows = collection.map((item) => `| ${item.id} | ${item.text} | ${item.fontSize}px | ${item.status} |`);
  fs.writeFileSync(
    path.join(qa, `${name}.md`),
    [`# ${name}`, "", `- 审查数量：${collection.length}/${expected}`, "- 结果：PASS", "", "| ID | 文案 | 字号 | 结果 |", "|---|---|---:|---|", ...rows, ""].join("\n"),
  );
}

async function renderAuditContact(collection, filename, boundsKey) {
  if (collection.length === 0) {
    const placeholder = Buffer.from(`<svg width="540" height="120" xmlns="http://www.w3.org/2000/svg"><rect width="100%" height="100%" fill="#d7d3cb"/><text x="270" y="60" text-anchor="middle" dominant-baseline="central" font-family="sans-serif" font-size="22" fill="#2a2927">No items in this audit</text></svg>`);
    await sharp(placeholder).jpeg({ quality: 94 }).toFile(path.join(ROOT, "qa", filename));
    return;
  }
  const tileW = 250;
  const tileH = 170;
  const labelH = 30;
  const gap = 14;
  const columns = 4;
  const rows = Math.ceil(collection.length / columns);
  const composites = [];
  for (let index = 0; index < collection.length; index += 1) {
    const item = collection[index];
    const match = item.id.match(/^P(\d+)-/);
    if (!match) throw new Error(`${item.id}: audit id must start with P<number>-`);
    const pageNumber = match[1].padStart(2, "0");
    const [x, y, width, height] = item[boundsKey];
    const pad = 18;
    const left = Math.max(0, Math.floor(x - pad));
    const top = Math.max(0, Math.floor(y - pad));
    const extractWidth = Math.min(W - left, Math.ceil(width + pad * 2));
    const extractHeight = Math.min(H - top, Math.ceil(height + pad * 2));
    const crop = await sharp(path.join(ROOT, `page-${pageNumber}.png`))
      .extract({ left, top, width: extractWidth, height: extractHeight })
      .resize(tileW, tileH, { fit: "contain", background: "#d7d3cb" })
      .jpeg({ quality: 94 })
      .toBuffer();
    const bar = Buffer.from(`<svg width="${tileW}" height="${labelH}" xmlns="http://www.w3.org/2000/svg"><rect width="100%" height="100%" fill="#2a2927"/><text x="10" y="21" font-family="sans-serif" font-size="16" font-weight="600" fill="#fff">${xml(item.id)} · GEOMETRY PASS</text></svg>`);
    const tile = await sharp({ create: { width: tileW, height: tileH + labelH, channels: 3, background: "#fff" } })
      .composite([{ input: bar, left: 0, top: 0 }, { input: crop, left: 0, top: labelH }])
      .jpeg({ quality: 94 })
      .toBuffer();
    composites.push({
      input: tile,
      left: gap + (index % columns) * (tileW + gap),
      top: gap + Math.floor(index / columns) * (tileH + labelH + gap),
    });
  }
  await sharp({
    create: {
      width: columns * tileW + (columns + 1) * gap,
      height: rows * (tileH + labelH) + (rows + 1) * gap,
      channels: 3,
      background: "#d7d3cb",
    },
  }).composite(composites).jpeg({ quality: 94 }).toFile(path.join(ROOT, "qa", filename));
}

async function main() {
  fs.mkdirSync(path.join(ROOT, "qa"), { recursive: true });
  const valid = new Set(layout.pages.map((page) => `page-${page.number}.png`));
  for (const file of fs.readdirSync(ROOT)) {
    if (/^page-\d\d\.png$/.test(file) && !valid.has(file)) fs.rmSync(path.join(ROOT, file));
  }
  for (const page of layout.pages) await renderPage(page);
  validateAuditCounts();
  await renderReviewContact();
  writeAudit("bubble-layout-audit", layout.expected_balloon_count, balloonAudit, "balloons");
  writeAudit("framed-text-layout-audit", layout.expected_framed_text_count, framedTextAudit, "items");
  await renderAuditContact(balloonAudit, "bubble-contact-sheet.jpg", "bubble");
  await renderAuditContact(framedTextAudit, "framed-text-contact-sheet.jpg", "frame");
  console.log(`Rendered ${layout.pages.length} pages with ${balloonAudit.length} balloons and ${framedTextAudit.length} framed texts.`);
}

main().catch((error) => {
  console.error(error.stack || error.message);
  process.exit(1);
});
