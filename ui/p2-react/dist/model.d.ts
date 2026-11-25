import type { P2PanelModels } from "./types.js";
/** Build typed, read-only panel models without adding joins or changing evidence. */
export declare function buildP2PanelModels(value: unknown): P2PanelModels;
/** Summarize refreshed membership evidence without treating missing rows as resolution. */
export declare function summarizeMembershipRefresh(value: unknown, targetWaferIds: readonly string[]): string[];
