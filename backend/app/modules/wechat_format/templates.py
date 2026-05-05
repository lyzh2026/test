import html
import re


def _split_paragraphs(text: str | None) -> list[str]:
    """Split raw text into paragraphs for WeChat article display.

    - Split on double newlines (paragraph boundaries)
    - Within each block, convert single newlines to <br>
    - Strip whitespace and skip empty blocks
    """
    if not text:
        return []
    text = text.replace("\r\n", "\n")
    blocks = re.split(r"\n\n+", text)
    result: list[str] = []
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        result.append(block)
    return result


def _escape_html(text: str) -> str:
    return html.escape(text, quote=False)


def _green_simple(
    title: str,
    paragraphs: list[str],
    summary: str = "",
    keywords: list[str] | None = None,
    source: str = "",
    date_str: str = "",
    link: str = "",
) -> str:
    """Green-accent WeChat template — clean, readable, warm."""
    parts: list[str] = []
    a = parts.append

    # Title
    escaped_title = _escape_html(title)
    a(f'<p style="text-align:center;font-size:17px;font-weight:bold;color:#2e7d32;line-height:1.6;margin:10px 0 4px;">{escaped_title}</p>')

    # Meta
    meta_parts = []
    if source:
        meta_parts.append(_escape_html(source))
    if date_str:
        meta_parts.append(_escape_html(date_str))
    if meta_parts:
        meta = " · ".join(meta_parts)
        a(f'<p style="text-align:center;font-size:13px;color:#999;margin:0 0 6px;">{meta}</p>')

    # Green divider
    a('<div style="width:50px;height:2px;background:#2e7d32;margin:0 auto 16px;"></div>')

    # Summary box
    if summary:
        escaped_summary = _escape_html(summary)
        a(
            '<div style="background:#e8f5e9;border-radius:6px;padding:12px 16px;'
            f'margin:0 0 16px;font-size:14px;color:#333;line-height:1.7;">'
            f'<span style="font-weight:bold;color:#2e7d32;">📖 摘要</span><br>'
            f'{escaped_summary}</div>'
        )

    # Body paragraphs
    for para in paragraphs:
        escaped_para = _escape_html(para).replace("\n", "<br>")
        a(
            '<p style="font-size:15px;line-height:1.75;color:#333;'
            f'margin:0 0 12px;text-align:justify;">{escaped_para}</p>'
        )

    # Keywords
    if keywords:
        kw_spans = []
        for kw in keywords:
            escaped_kw = _escape_html(kw)
            kw_spans.append(
                '<span style="display:inline-block;padding:2px 10px;'
                f'margin:0 6px 6px 0;font-size:12px;color:#2e7d32;'
                f'border:1px solid #2e7d32;border-radius:12px;">'
                f'{escaped_kw}</span>'
            )
        if kw_spans:
            a(
                '<div style="margin:16px 0 0;">'
                + "".join(kw_spans)
                + "</div>"
            )

    # Footer
    a('<hr style="border:none;border-top:1px solid #eee;margin:20px 0 10px;">')
    footer_parts = []
    if link:
        escaped_link = _escape_html(link)
        footer_parts.append(
            f'<a href="{escaped_link}" style="color:#2e7d32;text-decoration:none;">阅读原文</a>'
        )
    footer_parts.append('<span style="color:#bbb;">内容由拾讯自动排版</span>')
    a(
        '<p style="text-align:center;font-size:12px;color:#bbb;margin:6px 0;">'
        + " · ".join(footer_parts)
        + "</p>"
    )

    return "".join(parts)


def _clean_white(
    title: str,
    paragraphs: list[str],
    summary: str = "",
    keywords: list[str] | None = None,
    source: str = "",
    date_str: str = "",
    link: str = "",
) -> str:
    """Clean white WeChat template — minimalist, serif-friendly."""
    parts: list[str] = []
    a = parts.append

    # Title
    escaped_title = _escape_html(title)
    a(f'<p style="text-align:center;font-size:18px;font-weight:bold;color:#111;line-height:1.6;margin:12px 0 4px;">{escaped_title}</p>')

    # Meta
    meta_parts = []
    if source:
        meta_parts.append(_escape_html(source))
    if date_str:
        meta_parts.append(_escape_html(date_str))
    if meta_parts:
        meta = " · ".join(meta_parts)
        a(f'<p style="text-align:center;font-size:12px;color:#aaa;margin:0 0 6px;">{meta}</p>')

    # Thin divider
    a('<hr style="border:none;border-top:1px solid #e8e8e8;margin:0 0 20px;">')

    # Summary box — left border style
    if summary:
        escaped_summary = _escape_html(summary)
        a(
            '<div style="border-left:3px solid #ccc;padding:8px 14px;margin:0 0 20px;'
            f'font-size:14px;color:#666;line-height:1.7;">'
            f'{escaped_summary}</div>'
        )

    # Body paragraphs
    for para in paragraphs:
        escaped_para = _escape_html(para).replace("\n", "<br>")
        a(
            '<p style="font-size:16px;line-height:1.8;color:#444;'
            f'margin:0 0 14px;text-align:justify;">{escaped_para}</p>'
        )

    # Keywords
    if keywords:
        kw_spans = []
        for kw in keywords:
            escaped_kw = _escape_html(kw)
            kw_spans.append(
                '<span style="display:inline-block;padding:2px 8px;'
                f'margin:0 4px 4px 0;font-size:12px;color:#666;'
                f'background:#f5f5f5;border-radius:3px;">'
                f'{escaped_kw}</span>'
            )
        if kw_spans:
            a(
                '<div style="margin:16px 0 0;">'
                + "".join(kw_spans)
                + "</div>"
            )

    # Footer
    a('<hr style="border:none;border-top:1px solid #e8e8e8;margin:20px 0 10px;">')
    footer_parts = []
    if link:
        escaped_link = _escape_html(link)
        footer_parts.append(
            f'<a href="{escaped_link}" style="color:#999;text-decoration:none;">阅读原文</a>'
        )
    footer_parts.append('<span style="color:#ccc;">拾讯排版</span>')
    a(
        '<p style="text-align:center;font-size:11px;color:#ccc;margin:6px 0;">'
        + " · ".join(footer_parts)
        + "</p>"
    )

    return "".join(parts)


TEMPLATES: dict[str, callable] = {
    "green-simple": _green_simple,
    "clean-white": _clean_white,
}
