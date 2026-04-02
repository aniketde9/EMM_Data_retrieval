const { Document, Packer, Paragraph, TextRun, ImageRun, AlignmentType, BorderStyle, Header, Footer, PageNumber, ShadingType, LevelFormat } = require("docx");
const fs = require("fs");

const contentPath = process.argv[2];
const outputPath = process.argv[3];
const content = JSON.parse(fs.readFileSync(contentPath, "utf8"));

let logoImage = null;
if (content.logo_path && fs.existsSync(content.logo_path)) {
  logoImage = fs.readFileSync(content.logo_path);
}

const NAVY = "305A81";
const PINK = "FF4D71";
const DARK = "212C35";
const LIGHT_GREY = "F5F7FA";

function sectionHeader(text) {
  return new Paragraph({
    children: [new TextRun({ text, bold: true, size: 62, color: NAVY, font: "JetBrains Mono" })],
    spacing: { before: 480, after: 120 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: PINK, space: 4 } },
  });
}

function bodyPara(text, options = {}) {
  return new Paragraph({
    children: [new TextRun({ text: text || "", size: 22, color: DARK, font: "Roboto", ...options })],
    spacing: { before: 120, after: 120 },
  });
}

function calloutPara(text) {
  return new Paragraph({
    children: [new TextRun({ text: text || "", bold: true, size: 38, color: NAVY, font: "Roboto" })],
    shading: { fill: LIGHT_GREY, type: ShadingType.CLEAR },
    spacing: { before: 240, after: 240 },
    indent: { left: 480, right: 480 },
  });
}

const children = [];
children.push(new Paragraph({
  children: [new TextRun({ text: "Extra Mile Method", bold: true, size: 98, color: NAVY, font: "JetBrains Mono" })],
  alignment: AlignmentType.LEFT,
  spacing: { before: 0, after: 120 },
}));
children.push(new Paragraph({
  children: [new TextRun({ text: `A GTM Memo for ${content.author_name || ""}`, bold: true, size: 54, color: PINK, font: "JetBrains Mono" })],
  spacing: { before: 0, after: 480 },
}));

children.push(sectionHeader("We See You"));
children.push(bodyPara(content.we_see_you));
children.push(sectionHeader("The Gap"));
children.push(calloutPara(content.the_gap));
children.push(sectionHeader("What We Found"));
children.push(bodyPara(content.strategic_insight));

const sections = content.sections || {};
for (const section of Object.values(sections)) {
  if (section && section.static_content) {
    children.push(sectionHeader(section.label));
    children.push(bodyPara(section.static_content));
  }
}

children.push(sectionHeader("One Post. This Week."));
children.push(bodyPara(content.chapter_experiment));
children.push(sectionHeader("Ready to Publish"));
for (const post of [content.linkedin_post_1, content.linkedin_post_2, content.linkedin_post_3]) {
  if (post) {
    children.push(bodyPara(post, { italics: true }));
  }
}

children.push(sectionHeader("5-Email Sequence"));
for (const line of (content.email_hooks || "").split("\n").filter((l) => l.trim())) {
  children.push(bodyPara(line));
}

const doc = new Document({
  numbering: {
    config: [{
      reference: "bullets",
      levels: [{
        level: 0,
        format: LevelFormat.BULLET,
        text: "●",
        alignment: AlignmentType.LEFT,
        style: { run: { color: PINK, size: 22 }, paragraph: { indent: { left: 720, hanging: 360 } } },
      }],
    }],
  },
  sections: [{
    properties: {
      page: { size: { width: 12240, height: 15840 }, margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 } },
    },
    headers: {
      default: new Header({
        children: [new Paragraph({
          children: [
            new TextRun({ text: "OPIKA × EXTRA MILE METHOD", size: 14, color: "999999", font: "Roboto" }),
            new TextRun({ text: `\t${content.author_name || ""}`, size: 14, color: "999999", font: "Roboto" }),
          ],
          tabStops: [{ type: "right", position: 9360 }],
        })],
      }),
    },
    footers: {
      default: new Footer({
        children: [new Paragraph({
          children: [
            ...(logoImage ? [new ImageRun({ data: logoImage, type: "png", transformation: { width: 106, height: 46 } })] : [new TextRun({ text: "Opika", size: 16, bold: true, color: NAVY, font: "JetBrains Mono" })]),
            new TextRun({ text: "\t", size: 16 }),
            new TextRun({ children: [PageNumber.CURRENT], size: 16, color: "999999", font: "Roboto" }),
          ],
          tabStops: [{ type: "right", position: 9360 }],
        })],
      }),
    },
    children,
  }],
});

Packer.toBuffer(doc).then((buffer) => {
  fs.writeFileSync(outputPath, buffer);
  console.log(`Generated: ${outputPath}`);
});
