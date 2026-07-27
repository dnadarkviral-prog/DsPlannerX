import crypto from 'node:crypto';
import { del } from '@vercel/blob';

const verifyPlannerToken = (token) => {
  const sessionSecret = process.env.SESSION_SECRET || '';
  if (sessionSecret.length < 32) throw new Error('SESSION_SECRET não configurado.');

  const [expiresText, suppliedSignature] = String(token || '').split('.', 2);
  const expiresAt = Number(expiresText);
  if (!Number.isFinite(expiresAt) || expiresAt < Math.floor(Date.now() / 1000)) {
    throw new Error('Autorização expirada.');
  }

  const expectedSignature = crypto
    .createHmac('sha256', sessionSecret)
    .update(String(expiresText))
    .digest('hex');
  const suppliedBuffer = Buffer.from(String(suppliedSignature || ''), 'utf8');
  const expectedBuffer = Buffer.from(expectedSignature, 'utf8');
  if (
    suppliedBuffer.length !== expectedBuffer.length ||
    !crypto.timingSafeEqual(suppliedBuffer, expectedBuffer)
  ) {
    throw new Error('Autorização inválida.');
  }
};

const readBody = async (request) => {
  if (request.body && typeof request.body === 'object' && !Buffer.isBuffer(request.body)) {
    return request.body;
  }
  if (typeof request.body === 'string') return JSON.parse(request.body || '{}');
  if (Buffer.isBuffer(request.body)) return JSON.parse(request.body.toString('utf8') || '{}');
  const chunks = [];
  for await (const chunk of request) chunks.push(chunk);
  const raw = Buffer.concat(chunks).toString('utf8');
  return raw ? JSON.parse(raw) : {};
};

const isBlobUrl = (value) => {
  try {
    const parsed = new URL(String(value || ''));
    return parsed.protocol === 'https:' && parsed.hostname.endsWith('blob.vercel-storage.com');
  } catch {
    return false;
  }
};

export default async function handler(req, res) {
  if (req.method !== 'POST') {
    res.setHeader('Allow', 'POST');
    return res.status(405).json({ ok: false, error: 'Método não permitido.' });
  }

  try {
    const body = await readBody(req);
    verifyPlannerToken(body.auth);
    if (!isBlobUrl(body.url)) throw new Error('URL de arquivo inválida.');
    await del(body.url);
    return res.status(200).json({ ok: true });
  } catch (error) {
    console.error('DS-PLANNERX Blob delete error:', error);
    return res.status(400).json({
      ok: false,
      error: error instanceof Error ? error.message : 'Não foi possível excluir o arquivo.',
    });
  }
}
