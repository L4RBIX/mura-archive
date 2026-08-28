import { createVerify } from "node:crypto";
import { describe, expect, it } from "vitest";
import { isDevAuthAllowed, readDevAuthConfig } from "@/lib/auth/providers/dev/config";
import { devJwks, DEV_KEY_ID } from "@/lib/auth/providers/dev/keys";
import { mintDevToken, readUnverifiedExpiry } from "@/lib/auth/providers/dev/token";
import { toDevServerAuthSession } from "@/lib/auth/providers/dev/adapter";
import {
  decodeDevIdentity,
  encodeDevIdentity,
  subjectForEmail,
} from "@/lib/auth/providers/dev/identity-cookie";

/** A complete, valid local development environment. */
const LOCAL = {
  MURA_DEV_AUTH: "true",
  NODE_ENV: "development",
  DEV_AUTH_ISSUER: "http://127.0.0.1:3000/api/dev-auth",
  DEV_AUTH_AUDIENCE: "mura-core",
};

const IDENTITY = {
  subject: "dev|babushka@example.com",
  email: "babushka@example.com",
  displayName: "Бабушка",
};

describe("the development issuer cannot run outside development", () => {
  it("is off unless explicitly asked for", () => {
    expect(isDevAuthAllowed({ ...LOCAL, MURA_DEV_AUTH: undefined })).toBe(false);
    expect(isDevAuthAllowed({})).toBe(false);
  });

  it("refuses in a production build even when asked for", () => {
    expect(isDevAuthAllowed({ ...LOCAL, NODE_ENV: "production" })).toBe(false);
  });

  it("refuses on a deployment even when asked for", () => {
    // Someone setting the variable in a hosting dashboard must not get an
    // issuer that mints identities on request.
    expect(isDevAuthAllowed({ ...LOCAL, VERCEL_ENV: "production" })).toBe(false);
    expect(isDevAuthAllowed({ ...LOCAL, VERCEL_ENV: "preview" })).toBe(false);
  });

  it("allows a local development run", () => {
    expect(isDevAuthAllowed(LOCAL)).toBe(true);
    expect(isDevAuthAllowed({ ...LOCAL, VERCEL_ENV: "development" })).toBe(true);
  });

  it("is never selected merely because another provider is unconfigured", () => {
    // The failure mode this forbids: an operational gap becoming an auth bypass.
    expect(isDevAuthAllowed({ NODE_ENV: "development" })).toBe(false);
  });
});

describe("configuration", () => {
  it("requires an issuer and an audience", () => {
    expect(readDevAuthConfig({ ...LOCAL, DEV_AUTH_ISSUER: undefined }).ok).toBe(false);
    expect(readDevAuthConfig({ ...LOCAL, DEV_AUTH_AUDIENCE: undefined }).ok).toBe(false);
  });

  it("refuses configuration when the provider itself is not allowed", () => {
    const result = readDevAuthConfig({ ...LOCAL, NODE_ENV: "production" });
    expect(result).toEqual({ ok: false, reason: "dev_auth_not_allowed" });
  });

  it("returns issuer and audience when complete", () => {
    const result = readDevAuthConfig(LOCAL);
    expect(result.ok && result.config).toEqual({
      issuer: LOCAL.DEV_AUTH_ISSUER,
      audience: LOCAL.DEV_AUTH_AUDIENCE,
    });
  });
});

describe("the session decision table", () => {
  it("reports unconfigured, never signed in, when the provider is not allowed", () => {
    // A cookie must not be able to conjure a session in a build that should
    // have no development issuer at all.
    expect(toDevServerAuthSession(IDENTITY, { ...LOCAL, NODE_ENV: "production" })).toEqual({
      status: "provider_unconfigured",
    });
  });

  it("reports unauthenticated when nobody is signed in", () => {
    expect(toDevServerAuthSession(null, LOCAL)).toEqual({ status: "unauthenticated" });
  });

  it("mints an access token for a signed-in identity", () => {
    const session = toDevServerAuthSession(IDENTITY, LOCAL);
    expect(session.status).toBe("authenticated");
    expect(session.status === "authenticated" && session.accessToken.split(".")).toHaveLength(3);
  });
});

describe("the minted token", () => {
  const config = { issuer: LOCAL.DEV_AUTH_ISSUER, audience: LOCAL.DEV_AUTH_AUDIENCE };
  const now = 1_800_000_000;

  function decode(token: string) {
    const [header, payload] = token.split(".");
    return {
      header: JSON.parse(Buffer.from(header, "base64url").toString("utf8")),
      payload: JSON.parse(Buffer.from(payload, "base64url").toString("utf8")),
    };
  }

  it("is RS256 and names the key it was signed with", () => {
    const { header } = decode(mintDevToken({ identity: IDENTITY, config, now }));
    expect(header.alg).toBe("RS256");
    expect(header.kid).toBe(DEV_KEY_ID);
  });

  it("carries every claim Core verifies", () => {
    const { payload } = decode(mintDevToken({ identity: IDENTITY, config, now }));
    expect(payload.iss).toBe(config.issuer);
    expect(payload.aud).toBe(config.audience);
    expect(payload.sub).toBe(IDENTITY.subject);
    expect(payload.exp).toBeGreaterThan(now);
    expect(payload.nbf).toBeLessThanOrEqual(now);
  });

  it("carries no authorization claims", () => {
    // Family, role and person id are read from the database per request. Baked
    // into a token they would be stale the moment an owner changed a role.
    const { payload } = decode(mintDevToken({ identity: IDENTITY, config, now }));
    expect(payload).not.toHaveProperty("family_id");
    expect(payload).not.toHaveProperty("role");
    expect(payload).not.toHaveProperty("person_id");
    expect(payload).not.toHaveProperty("speaker_person_id");
  });

  it("verifies against the published JWKS", () => {
    const token = mintDevToken({ identity: IDENTITY, config, now });
    const [header, payload, signature] = token.split(".");

    const jwk = devJwks().keys[0];
    // Reconstructed from the *published* key, so this proves the JWKS Core
    // fetches genuinely verifies the tokens this issuer mints.
    const publicKey = { key: { ...jwk, kty: "RSA" }, format: "jwk" as const };
    const verifier = createVerify("RSA-SHA256");
    verifier.update(`${header}.${payload}`);
    verifier.end();

    expect(verifier.verify(publicKey, Buffer.from(signature, "base64url"))).toBe(true);
  });

  it("does not verify once a character is altered", () => {
    const token = mintDevToken({ identity: IDENTITY, config, now });
    const [header, payload, signature] = token.split(".");
    const tampered = JSON.parse(Buffer.from(payload, "base64url").toString("utf8"));
    tampered.sub = "dev|someone-else@example.com";
    const forged = Buffer.from(JSON.stringify(tampered), "utf8").toString("base64url");

    const jwk = devJwks().keys[0];
    const verifier = createVerify("RSA-SHA256");
    verifier.update(`${header}.${forged}`);
    verifier.end();

    expect(
      verifier.verify(
        { key: { ...jwk, kty: "RSA" }, format: "jwk" as const },
        Buffer.from(signature, "base64url"),
      ),
    ).toBe(false);
  });

  it("publishes only the public half", () => {
    const jwk = devJwks().keys[0];
    expect(jwk.kty).toBe("RSA");
    // Private RSA parameters. Any of these in a JWKS would publish the key.
    for (const secret of ["d", "p", "q", "dp", "dq", "qi"]) {
      expect(jwk).not.toHaveProperty(secret);
    }
  });

  it("reads its own expiry back", () => {
    const token = mintDevToken({ identity: IDENTITY, config, now, ttlSeconds: 900 });
    expect(readUnverifiedExpiry(token)).toBe(now + 900);
  });

  it("returns no expiry for a malformed token", () => {
    expect(readUnverifiedExpiry("not-a-token")).toBeNull();
    expect(readUnverifiedExpiry("a.b")).toBeNull();
  });
});

describe("the identity cookie", () => {
  it("round-trips an identity", () => {
    expect(decodeDevIdentity(encodeDevIdentity(IDENTITY))).toEqual(IDENTITY);
  });

  it("gives one email one stable subject", () => {
    expect(subjectForEmail("Babushka@Example.com ")).toBe(subjectForEmail("babushka@example.com"));
  });

  it("rejects anything that is not a complete identity", () => {
    // A half-formed value must not become a user with an empty subject.
    expect(decodeDevIdentity(undefined)).toBeNull();
    expect(decodeDevIdentity("not-base64url-json")).toBeNull();
    expect(
      decodeDevIdentity(Buffer.from(JSON.stringify({ email: "a@b.c" })).toString("base64url")),
    ).toBeNull();
    expect(
      decodeDevIdentity(
        Buffer.from(JSON.stringify({ subject: "", email: "a@b.c", displayName: "x" })).toString(
          "base64url",
        ),
      ),
    ).toBeNull();
  });
});
