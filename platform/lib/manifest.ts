import * as fs from 'fs';
import * as path from 'path';
import * as YAML from 'yaml';

/** A single MCP tool definition (subset of the Gateway ToolDefinition schema). */
export interface ToolDef {
  name: string;
  description: string;
  inputSchema: Record<string, unknown>;
  outputSchema?: Record<string, unknown>;
}

/** Parsed capability manifest (capabilities/mcp/<name>/manifest.yaml). */
export interface McpCapabilityManifest {
  name: string;
  description: string;
  type: 'lambda' | 'awslabs-reuse' | 'mcp-passthrough' | 'external-repo';
  enabled: boolean;
  owner?: string;
  handler?: string; // type: lambda — relative path to handler file within the capability dir
  runtime?: string; // optional lambda runtime override
  endpoint?: { ssmParameter?: string; url?: string }; // external-repo / mcp-passthrough
  /**
   * type: lambda — optional read-only data pack. `dir` (relative to the capability
   * directory) is seeded to a dedicated S3 bucket at deploy; the bucket name is
   * injected into the Lambda via `envVar`. The Lambda gets read-only access.
   */
  data?: { dir: string; envVar: string };
  source?: string; // external-repo — the owning repository
  retirement?: string;
  tools?: ToolDef[];
  permissions?: string[]; // IAM actions, least-privilege, read-only
  readOnly: boolean;
  dir: string; // resolved absolute path of the capability directory
}

const WRITE_ACTION_PATTERN =
  /:(Create|Put|Delete|Update|Modify|Terminate|Start|Stop|Reboot|Attach|Detach|Associate|Disassociate|Run|Invoke\w+Write|Write)/i;

/**
 * Scan capabilities/mcp/ for manifests. Enforces the governance contract:
 *  - readOnly must be true for every Gateway target (writes belong in A2A agents)
 *  - declared permissions must not contain mutating actions
 */
export function loadMcpManifests(capabilitiesRoot: string): McpCapabilityManifest[] {
  const mcpRoot = path.join(capabilitiesRoot, 'mcp');
  if (!fs.existsSync(mcpRoot)) return [];

  const manifests: McpCapabilityManifest[] = [];
  const walk = (dir: string) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      if (!entry.isDirectory()) continue;
      const sub = path.join(dir, entry.name);
      const manifestPath = path.join(sub, 'manifest.yaml');
      if (fs.existsSync(manifestPath)) {
        const raw = YAML.parse(fs.readFileSync(manifestPath, 'utf-8'));
        const m: McpCapabilityManifest = { ...raw, dir: sub };
        validate(m, manifestPath);
        manifests.push(m);
      } else {
        walk(sub); // allow grouping dirs like examples/
      }
    }
  };
  walk(mcpRoot);
  return manifests;
}

function validate(m: McpCapabilityManifest, file: string): void {
  if (!m.name) throw new Error(`${file}: 'name' is required`);
  if (m.readOnly !== true) {
    throw new Error(
      `${file}: readOnly must be true — write capabilities are rejected on the shared Gateway. ` +
        `Write paths belong in capabilities/a2a/ agents with isolated credentials.`
    );
  }
  for (const action of m.permissions ?? []) {
    if (WRITE_ACTION_PATTERN.test(action)) {
      throw new Error(
        `${file}: permission '${action}' looks mutating. Gateway targets are read-only by contract.`
      );
    }
  }
  if (m.type === 'lambda' && m.enabled && !m.handler) {
    throw new Error(`${file}: type 'lambda' requires 'handler'`);
  }
  if (m.type === 'lambda' && m.enabled && (!m.tools || m.tools.length === 0)) {
    throw new Error(`${file}: type 'lambda' requires at least one tool definition`);
  }
  if (m.data && (!m.data.dir || !m.data.envVar)) {
    throw new Error(`${file}: 'data' requires both 'dir' and 'envVar'`);
  }
}
