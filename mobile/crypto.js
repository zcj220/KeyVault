// 与 keyvault/crypto.py 同一套：KVAULT1 + PBKDF2 + Fernet
const ITERATIONS = 390000;
const MAGIC = new TextEncoder().encode("KVAULT1\n");

function concat(...parts) {
  const size = parts.reduce((n, p) => n + p.length, 0);
  const out = new Uint8Array(size);
  let offset = 0;
  for (const part of parts) {
    out.set(part, offset);
    offset += part.length;
  }
  return out;
}

function startsWith(bytes, prefix) {
  if (bytes.length < prefix.length) return false;
  for (let i = 0; i < prefix.length; i += 1) {
    if (bytes[i] !== prefix[i]) return false;
  }
  return true;
}

function bytesToB64Url(bytes) {
  let binary = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_");
}

function b64UrlToBytes(text) {
  let s = String(text).trim().replace(/-/g, "+").replace(/_/g, "/");
  while (s.length % 4) s += "=";
  const binary = atob(s);
  const out = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) out[i] = binary.charCodeAt(i);
  return out;
}

function equalBytes(a, b) {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i += 1) diff |= a[i] ^ b[i];
  return diff === 0;
}

async function sha256(bytes) {
  return new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
}

async function pbkdf2(password, salt) {
  const material = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(password),
    "PBKDF2",
    false,
    ["deriveBits"]
  );
  const bits = await crypto.subtle.deriveBits(
    { name: "PBKDF2", salt, iterations: ITERATIONS, hash: "SHA-256" },
    material,
    256
  );
  return new Uint8Array(bits);
}

function splitKey(rawKey) {
  return { signKey: rawKey.slice(0, 16), encKey: rawKey.slice(16) };
}

async function hmac(signKey, data) {
  const key = await crypto.subtle.importKey(
    "raw",
    signKey,
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  return new Uint8Array(await crypto.subtle.sign("HMAC", key, data));
}

function timestampBytes() {
  const ts = Math.floor(Date.now() / 1000);
  const buf = new ArrayBuffer(8);
  const view = new DataView(buf);
  view.setUint32(0, Math.floor(ts / 0x100000000));
  view.setUint32(4, ts >>> 0);
  return new Uint8Array(buf);
}

async function fernetEncrypt(rawKey, plaintext) {
  const { signKey, encKey } = splitKey(rawKey);
  const iv = crypto.getRandomValues(new Uint8Array(16));
  const aes = await crypto.subtle.importKey("raw", encKey, "AES-CBC", false, ["encrypt"]);
  const cipher = new Uint8Array(
    await crypto.subtle.encrypt({ name: "AES-CBC", iv }, aes, plaintext)
  );
  const basic = concat(Uint8Array.of(0x80), timestampBytes(), iv, cipher);
  const mac = await hmac(signKey, basic);
  return new TextEncoder().encode(bytesToB64Url(concat(basic, mac)));
}

async function fernetDecrypt(rawKey, tokenBytes) {
  const { signKey, encKey } = splitKey(rawKey);
  const text = new TextDecoder().decode(tokenBytes).trim();
  const raw = b64UrlToBytes(text);
  if (raw.length < 1 + 8 + 16 + 32 || raw[0] !== 0x80) {
    throw new Error("bad-token");
  }
  const basic = raw.slice(0, raw.length - 32);
  const given = raw.slice(raw.length - 32);
  const expect = await hmac(signKey, basic);
  if (!equalBytes(given, expect)) throw new Error("bad-token");
  const iv = basic.slice(9, 25);
  const cipher = basic.slice(25);
  const aes = await crypto.subtle.importKey("raw", encKey, "AES-CBC", false, ["decrypt"]);
  try {
    const plain = await crypto.subtle.decrypt({ name: "AES-CBC", iv }, aes, cipher);
    return new Uint8Array(plain);
  } catch {
    throw new Error("bad-token");
  }
}

export async function decryptVault(password, buffer) {
  const bytes = buffer instanceof Uint8Array ? buffer : new Uint8Array(buffer);
  if (!startsWith(bytes, MAGIC)) throw new Error("bad-file");
  const body = bytes.slice(MAGIC.length);
  if (body.length < 16 + 8 + 16) throw new Error("bad-file");
  const salt = body.slice(0, 16);
  const check = body.slice(16, 24);
  const token = body.slice(24);
  const expected = (await sha256(concat(new TextEncoder().encode(password), salt))).slice(0, 8);
  if (!equalBytes(check, expected)) throw new Error("bad-password");
  const rawKey = await pbkdf2(password, salt);
  const plain = await fernetDecrypt(rawKey, token);
  return JSON.parse(new TextDecoder().decode(plain));
}

export async function encryptVault(password, data) {
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const rawKey = await pbkdf2(password, salt);
  const plain = new TextEncoder().encode(JSON.stringify(data));
  const token = await fernetEncrypt(rawKey, plain);
  const check = (await sha256(concat(new TextEncoder().encode(password), salt))).slice(0, 8);
  return concat(MAGIC, salt, check, token);
}
