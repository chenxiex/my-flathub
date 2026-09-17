import { setupNetwork } from '@msw/cloudflare';
import { exports } from 'cloudflare:workers';
import { http, HttpResponse } from 'msw';
import { afterAll, afterEach, beforeAll, expect, it } from 'vitest';

const network = setupNetwork();
const assetUrl = 'https://github.com/chenxiex/my-flathub/releases/download/pr-preview-12-345-2/f-289e1ddab324721400fa4f463e9eb4c7e53083484d57b0a79eb2c7068baa7510';

beforeAll(() => network.enable());
afterEach(() => network.resetHandlers());
afterAll(() => network.disable());

it('仓库路径映射到对应的 Release 附件并保留 Range', async () => {
    let received = false;
    network.use(http.get(assetUrl, ({ request }) => {
        received = true;
        expect(request.headers.get('Range')).toBe('bytes=0-2');
        return HttpResponse.text('abc', {
            status: 206,
            headers: { 'Content-Range': 'bytes 0-2/10' },
        });
    }));

    const response = await exports.default.fetch(new Request(
        'https://preview.example/pr/12/345-2/objects/ab/example.filez',
        { headers: { Range: 'bytes=0-2' } },
    ));
    expect(received).toBe(true);
    expect(response.status).toBe(206);
    expect(await response.text()).toBe('abc');
    expect(response.headers.get('Content-Range')).toBe('bytes 0-2/10');
    expect(response.headers.get('Cache-Control')).toBe('public, max-age=432000, immutable');
});

it('拒绝路径穿越和写入请求', async () => {
    const invalid = await exports.default.fetch('https://preview.example/pr/12/345-2/objects/%2F..%2Fsecret');
    const method = await exports.default.fetch(new Request(
        'https://preview.example/pr/12/345-2/summary',
        { method: 'POST' },
    ));
    expect(invalid.status).toBe(404);
    expect(method.status).toBe(405);
});

it('描述文件返回正确的类型并禁用缓存', async () => {
    network.use(http.get(/https:\/\/github\.com\/.*\/releases\/download\/.*\/.*/, () => {
        return HttpResponse.text('[Flatpak Repo]');
    }));
    const response = await exports.default.fetch('https://preview.example/pr/12/345-2/repo.flatpakrepo');
    expect(response.headers.get('Content-Type')).toBe('application/vnd.flatpak.repo');
    expect(response.headers.get('Cache-Control')).toBe('no-cache');
});

it('条件请求的 304 响应不包含正文', async () => {
    network.use(http.get(/https:\/\/github\.com\/.*\/releases\/download\/.*\/.*/, () => {
        return new HttpResponse(null, { status: 304 });
    }));
    const response = await exports.default.fetch('https://preview.example/pr/12/345-2/summary');
    expect(response.status).toBe(304);
    expect(await response.text()).toBe('');
});
