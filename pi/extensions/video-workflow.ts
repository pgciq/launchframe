import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const extensionRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../..");

function cliPath(): string {
  const windows = join(extensionRoot, ".venv", "Scripts", "ai-video.exe");
  const posix = join(extensionRoot, ".venv", "bin", "ai-video");
  if (process.platform === "win32" && existsSync(windows)) return windows;
  if (existsSync(posix)) return posix;
  return process.platform === "win32" ? "ai-video.exe" : "ai-video";
}

async function runCli(args: string[], ctx: any, extraEnv: Record<string, string> = {}): Promise<void> {
  const child = spawn(cliPath(), args, {
    cwd: extensionRoot,
    env: { ...process.env, ...extraEnv },
    stdio: ["ignore", "pipe", "pipe"],
    shell: false,
  });
  let output = "";
  child.stdout.on("data", (chunk) => { output += chunk.toString(); });
  child.stderr.on("data", (chunk) => { output += chunk.toString(); });
  await new Promise<void>((resolvePromise, reject) => {
    child.on("error", reject);
    child.on("close", (code) => code === 0 ? resolvePromise() : reject(new Error(output || `ai-video exited with ${code}`)));
  });
  ctx.ui.notify(output.trim() || "Video operation completed.", "info");
}

async function projectInput(ctx: any, args: string): Promise<string | undefined> {
  const value = args.trim() || await ctx.ui.input("Product project directory", "D:\\video-projects\\my-product");
  return value?.trim() || undefined;
}

export default function (pi: ExtensionAPI) {
  pi.registerCommand("video-scan", {
    description: "Scan and categorize product video resources",
    handler: async (args, ctx) => {
      const project = await projectInput(ctx, args);
      if (project) await runCli(["scan", project], ctx);
    },
  });

  pi.registerCommand("video-status", {
    description: "Show the latest video workflow status",
    handler: async (args, ctx) => {
      const project = await projectInput(ctx, args);
      if (project) await runCli(["status", project], ctx);
    },
  });

  pi.registerCommand("video-inspect", {
    description: "Validate a product video project configuration",
    handler: async (args, ctx) => {
      const project = await projectInput(ctx, args);
      if (project) await runCli(["inspect", project], ctx);
    },
  });

  pi.registerCommand("video-draft", {
    description: "Ask the selected CodeMie model to create a reviewable content draft",
    handler: async (args, ctx) => {
      const project = await projectInput(ctx, args);
      if (!project) return;
      pi.sendUserMessage(
        `Work on the product video project at ${project}. Inspect its product materials and images. Produce a factual, structured JSON draft with keys outline, primary_narration, and secondary_narration. The primary language is English and the configured secondary language should be used. Save the JSON to ${project}/.video-work/content-draft.json and save the two narration arrays to narration-primary.json and narration-secondary.json in the same directory. Do not build the PPT or video yet. Ask for human review after writing the files.`,
        { deliverAs: "followUp" },
      );
      ctx.ui.notify("Draft request sent to the selected CodeMie model. Review .video-work/content-draft.json before building.", "info");
    },
  });

  pi.registerCommand("video-build", {
    description: "Build PPT, narration, subtitles, PDF, and videos",
    handler: async (args, ctx) => {
      const project = await projectInput(ctx, args);
      if (!project) return;
      if (!await ctx.ui.confirm("Build video project?", "This calls Azure Speech and writes local outputs.")) return;
      await runCli(["build", project], ctx, { VIDEO_MCP_USE_EXISTING_DRAFT: "true" });
    },
  });


  pi.registerCommand("video-model-help", {
    description: "Show how to use CodeMie SSO and select a model",
    handler: async (_args, ctx) => {
      ctx.ui.notify("Use /login codemie, then /model or Ctrl+P to select a company model. Vision-capable models are required for image analysis.", "info");
    },
  });
}
