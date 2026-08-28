import { generateKeyPairSync, createPrivateKey, createPublicKey, type KeyObject } from "node:crypto";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";

/**
 * The RSA key this development issuer signs with.
 *
 * Generated once and kept on disk, because the alternative — a fresh key per
 * server start — invalidates every token already issued and every JWKS response
 * Core has cached, so a Turbopack reload would silently sign users out with an
 * `invalid_token` that looks like a bug in the auth code.
 *
 * The file is a private key. It lives under a gitignored directory and matches
 * the repository's existing `*.pem` ignore rule, and nothing ever logs or
 * returns it. It is a development credential for an issuer that cannot run
 * outside development (see `config.ts`), but it is still a private key and is
 * treated as one.
 */

const KEY_DIRECTORY = ".dev-auth";
const KEY_FILE = "issuer-key.pem";

/** Names the key in the JWKS and in each token header, so rotation is possible. */
export const DEV_KEY_ID = "mura-dev-issuer";

interface DevKeyPair {
  privateKey: KeyObject;
  publicKey: KeyObject;
}

let cached: DevKeyPair | null = null;

function keyPath(): string {
  return resolve(process.cwd(), KEY_DIRECTORY, KEY_FILE);
}

function loadFromDisk(): KeyObject | null {
  try {
    const pem = readFileSync(keyPath(), "utf8");
    return createPrivateKey(pem);
  } catch {
    // Absent on first run, and unreadable if it was truncated by an interrupted
    // write. Both mean "generate a new one" rather than "fail the request".
    return null;
  }
}

function generateAndPersist(): KeyObject {
  const { privateKey } = generateKeyPairSync("rsa", { modulusLength: 2048 });
  const pem = privateKey.export({ type: "pkcs8", format: "pem" }) as string;
  const path = keyPath();
  mkdirSync(dirname(path), { recursive: true });
  // Owner-only. The default 0644 would leave a private key world-readable.
  writeFileSync(path, pem, { mode: 0o600 });
  return privateKey;
}

/** The issuer's key pair, generated on first use and stable thereafter. */
export function devKeyPair(): DevKeyPair {
  if (cached) return cached;
  const privateKey = loadFromDisk() ?? generateAndPersist();
  cached = { privateKey, publicKey: createPublicKey(privateKey) };
  return cached;
}

/** JWK Set describing the public half, for Core to fetch and verify against. */
export function devJwks(): { keys: Array<Record<string, string>> } {
  const { publicKey } = devKeyPair();
  const jwk = publicKey.export({ format: "jwk" }) as Record<string, string>;
  return {
    keys: [
      {
        ...jwk,
        kid: DEV_KEY_ID,
        use: "sig",
        // Stated explicitly so a verifier never has to infer the algorithm from
        // the token's own header, which is where algorithm-confusion starts.
        alg: "RS256",
      },
    ],
  };
}

/** Drops the in-process cache. Tests only. */
export function resetDevKeyCacheForTests(): void {
  cached = null;
}
