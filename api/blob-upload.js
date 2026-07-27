import crypto from 'node:crypto';
import { handleUpload } from '@vercel/blob/client';

const ALLOWED_EXTENSIONS = new Set([
  'mp4', 'mov', 'mkv', 'avi', 'webm', 'm4v',
  'mp3', 'wav', 'm4a', 'aac', 'ogg', 'flac',
  'png', 'jpg', 'jpeg', 'webp', 'gif', 'svg',
  'txt', 'md', 'srt', 'pdf',
]);

const contentTypeFor = (pathname, requestedType) => {
  const extension = String(pathname || '').split('.').pop()?.toLowerCase() || '';
  if (!ALLOWED_EXTENSIONS.has(extension)) {
    throw new Error(`Formato não permitido: .${extension || 'sem extensão'}`);
  }

  const safeRequestedType = String(requestedType || '').trim();
  return safeRequestedType || 'application/octet-stream';
};

const parsePayload = (clientPayload) => {
  if (!clientPayload) return {};
  if (typeof clientPayload === 'object') return clientPayload;
  try {
    return JSON.parse(clientPayload);
  } catch {
    return {};
  }
};

const verifyPlannerToken = (token) => {
  const sessionSecret = process.env.SESSION_SECRET || '';
  if (sessionSecret.length < 32) {
    throw new Error('SESSION_SECRET não foi configurado corretamente.');
  }

  const [expiresText, suppliedSignature] = String(token || '').split('.', 2);
  const expiresAt = Number(expiresText);
  if (!Number.isFinite(expiresAt) || expiresAt < Math.floor(Date.now() / 1000)) {
    throw new Error('A autorização de upload expirou. Atualize a página e tente novamente.');
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
    throw new Error('Autorização de upload inválida.');
  }
};

const readBody = async (request) => {
  if (request.body && typeof request.body === 'object' && !Buffer.isBuffer(request.body)) {
    return request.body;
  }

  if (typeof request.body === 'string') {
    return JSON.parse(request.body || '{}');
  }
  if (Buffer.isBuffer(request.body)) {
    return JSON.parse(request.body.toString('utf8') || '{}');
  }

  const chunks = [];
  for await (const chunk of request) chunks.push(chunk);
  const raw = Buffer.concat(chunks).toString('utf8');
  return raw ? JSON.parse(raw) : {};
};

export default async function handler(req, res) {
  if (req.method !== 'POST') {
    res.setHeader('Allow', 'POST');
    return res.status(405).json({ error: 'Método não permitido.' });
  }

  try {
    const body = await readBody(req);
    const protocol = String(req.headers['x-forwarded-proto'] || 'https').split(',')[0];
    const host = req.headers.host || 'localhost';
    const headers = new Headers();
    for (const [key, value] of Object.entries(req.headers || {})) {
      if (Array.isArray(value)) value.forEach((item) => headers.append(key, item));
      else if (value !== undefined) headers.set(key, String(value));
    }
    headers.set('content-type', 'application/json');
    const webRequest = new Request(`${protocol}://${host}${req.url || '/api/blob-upload'}`, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
    });

    const jsonResponse = await handleUpload({
      body,
      request: webRequest,
      onBeforeGenerateToken: async (pathname, clientPayload) => {
        const payload = parsePayload(clientPayload);
        verifyPlannerToken(payload.auth);
        const contentType = contentTypeFor(pathname, payload.contentType);

        return {
          allowedContentTypes: [contentType],
          maximumSizeInBytes: 5 * 1024 * 1024 * 1024,
          addRandomSuffix: false,
          tokenPayload: JSON.stringify({ source: 'ds-plannerx' }),
        };
      },
      onUploadCompleted: async () => {
        // O formulário Python grava os metadados no Postgres depois que o
        // navegador confirma que o arquivo chegou ao Vercel Blob.
      },
    });

    return res.status(200).json(jsonResponse);
  } catch (error) {
    console.error('DS-PLANNERX Blob upload error:', error);
    return res.status(400).json({
      error: error instanceof Error ? error.message : 'Não foi possível autorizar o upload.',
    });
  }
}
