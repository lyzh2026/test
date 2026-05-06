/**
 * 下载文件并让用户选择保存路径（仅 Chromium 浏览器支持 showSaveFilePicker）。
 * 不支持时回退到普通 <a download> 行为。
 */
export async function downloadWithPicker(
  url: string,
  defaultFilename: string,
  init?: RequestInit,
) {
  // @ts-expect-error showSaveFilePicker is Chromium-only
  if (typeof window !== 'undefined' && typeof window.showSaveFilePicker === 'function') {
    try {
      // @ts-expect-error showSaveFilePicker
      const handle = await window.showSaveFilePicker({
        suggestedName: defaultFilename,
        types: [
          {
            description: '文件',
            accept: { 'application/octet-stream': [`.${defaultFilename.split('.').pop()}`] },
          },
        ],
      });
      const res = await fetch(url, init);
      if (!res.ok) throw new Error(`下载失败: ${res.status}`);
      const blob = await res.blob();
      const writable = await handle.createWritable();
      await writable.write(blob);
      await writable.close();
      return;
    } catch (e: unknown) {
      // 用户取消了 picker，不降级
      if (e instanceof DOMException && e.name === 'AbortError') return;
      // 其他错误降级到普通下载
    }
  }

  // Fallback: 普通下载
  if (init?.method && init.method !== 'GET') {
    const res = await fetch(url, init);
    if (!res.ok) throw new Error(`下载失败: ${res.status}`);
    const blob = await res.blob();
    const blobUrl = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = blobUrl;
    a.download = defaultFilename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(blobUrl);
  } else {
    const a = document.createElement('a');
    a.href = url;
    a.download = defaultFilename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }
}
