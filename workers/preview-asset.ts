export async function assetName(path: string): Promise<string> {
    const bytes = new TextEncoder().encode(path);
    const digest = await crypto.subtle.digest('SHA-256', bytes);
    return 'f-' + [...new Uint8Array(digest)]
        .map((byte) => byte.toString(16).padStart(2, '0'))
        .join('');
}
