import { assetName } from './preview-asset.ts';

const repository = 'chenxiex/my-flathub';
const route = /^\/pr\/([1-9][0-9]*)\/([1-9][0-9]*-[1-9][0-9]*)\/(.+)$/;
const pathPart = /^[A-Za-z0-9._+-]+$/;

const worker = {
    async fetch(request) {
        if (request.method !== 'GET' && request.method !== 'HEAD') {
            return new Response('不支持的请求方法', {
                status: 405,
                headers: { Allow: 'GET, HEAD' },
            });
        }

        const url = new URL(request.url);
        let path: string;
        try {
            path = decodeURIComponent(url.pathname);
        } catch {
            return new Response('无效路径', { status: 400 });
        }
        const match = route.exec(path);
        if (
            !match ||
            !match[3].split('/').every((part) =>
                pathPart.test(part) && part !== '.' && part !== '..'
            )
        ) {
            return new Response('未找到仓库文件', { status: 404 });
        }

        const [, number, previewId, relativePath] = match;
        const tag = `pr-preview-${number}-${previewId}`;
        const name = await assetName(relativePath);
        const upstreamUrl =
            `https://github.com/${repository}/releases/download/${tag}/${name}`;
        const headers = new Headers();
        for (
            const key of [
                'Range',
                'If-Range',
                'If-None-Match',
                'If-Modified-Since',
            ]
        ) {
            if (request.headers.has(key)) {
                headers.set(key, request.headers.get(key)!);
            }
        }
        let upstream: Response;
        try {
            upstream = await fetch(upstreamUrl, {
                method: request.method,
                headers,
                redirect: 'follow',
            });
        } catch {
            return new Response('上游仓库暂时不可用', { status: 502 });
        }
        const responseHeaders = new Headers(upstream.headers);
        responseHeaders.delete('content-disposition');
        responseHeaders.delete('set-cookie');
        if (relativePath === 'repo.flatpakrepo') {
            responseHeaders.set('content-type', 'application/vnd.flatpak.repo');
        }
        if (relativePath.startsWith('objects/')) {
            responseHeaders.set(
                'cache-control',
                'public, max-age=432000, immutable',
            );
        } else {
            responseHeaders.set('cache-control', 'no-cache');
        }
        const noBody = request.method === 'HEAD' ||
            [204, 205, 304].includes(upstream.status);
        return new Response(noBody ? null : upstream.body, {
            status: upstream.status,
            headers: responseHeaders,
        });
    },
} satisfies ExportedHandler<Env>;

export default worker;
