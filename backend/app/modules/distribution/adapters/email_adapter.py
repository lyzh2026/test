"""邮件通道适配器。"""
import asyncio
import logging
import smtplib
from email.mime.text import MIMEText

from app.modules.distribution.adapters.base import DistributionAdapter
from app.modules.distribution.schemas import WeeklyReport

logger = logging.getLogger("shixun.distribution.email")


def _build_html(report: WeeklyReport) -> str:
    """渲染周报 HTML 邮件正文。"""
    rows = ""
    for cat in report.categories:
        articles_html = ""
        for a in cat.articles:
            articles_html += f"""\
<tr style="border-bottom:1px solid #eee;">
  <td style="padding:10px 8px;vertical-align:top;">
    <a href="{a.url}" style="color:#1a73e8;text-decoration:none;font-weight:500;">{a.title}</a>
    <div style="color:#666;font-size:12px;margin-top:2px;">{a.source_unit} · {a.publish_date}</div>
    <div style="color:#333;font-size:13px;margin-top:4px;line-height:1.5;">{a.summary}</div>
  </td>
</tr>"""
        rows += f"""\
<tr><td style="padding:12px 0 4px;"><h3 style="margin:0;color:#333;">📋 {cat.name}（{len(cat.articles)}篇）</h3></td></tr>
{articles_html}"""

    return f"""\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,sans-serif;padding:20px;background:#f5f5f5;">
<div style="max-width:640px;margin:0 auto;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.1);">
<div style="background:#1a73e8;padding:20px;color:#fff;">
  <h1 style="margin:0;font-size:20px;">拾讯周报 {report.year_week}</h1>
  <p style="margin:4px 0 0;font-size:13px;opacity:0.9;">{report.date_range_start} ~ {report.date_range_end}</p>
</div>
<div style="padding:16px 20px;background:#e8f0fe;font-size:13px;color:#555;">
  本周共采集 <strong>{report.stats.total_articles}</strong> 篇文章，覆盖 <strong>{report.stats.total_categories}</strong> 个分类
</div>
{_build_health_block(report)}
<div style="padding:0 20px 20px;">
  <table style="width:100%;border-collapse:collapse;">
    {rows}
  </table>
</div>
<div style="padding:12px 20px;font-size:11px;color:#999;border-top:1px solid #eee;text-align:center;">
  本邮件由拾讯系统自动发送
</div>
</div>
</body>
</html>"""


def _build_health_block(report) -> str:
    """系统健康度区块；health 为 None 时不渲染。"""
    if not report.health:
        return ""
    h = report.health
    rows = "".join(
        f'<tr><td style="padding:4px 8px;border-bottom:1px solid #eee;">{s.domain}</td>'
        f'<td style="padding:4px 8px;border-bottom:1px solid #eee;text-align:right;">{s.attempts}</td>'
        f'<td style="padding:4px 8px;border-bottom:1px solid #eee;text-align:right;">{s.fail_count}</td>'
        f'<td style="padding:4px 8px;border-bottom:1px solid #eee;text-align:right;">{s.fail_rate:.0%}</td></tr>'
        for s in h.degraded_sites
    )
    table = (
        '<table style="width:100%;border-collapse:collapse;font-size:12px;">'
        '<tr><th style="text-align:left;padding:4px 8px;">站点</th>'
        '<th style="text-align:right;padding:4px 8px;">尝试</th>'
        '<th style="text-align:right;padding:4px 8px;">失败</th>'
        '<th style="text-align:right;padding:4px 8px;">失败率</th></tr>'
        f"{rows}</table>"
    ) if h.degraded_sites else '<p style="font-size:12px;color:#777;">本周无降级记录</p>'

    return (
        '<div style="padding:16px 20px;font-size:13px;color:#555;">'
        '<h3 style="margin:0 0 8px;font-size:14px;color:#333;">系统健康度</h3>'
        f'<p style="margin:0 0 8px;">总请求 <strong>{h.total_attempts}</strong>，'
        f'失败 <strong>{h.fail_count}</strong>，失败率 <strong>{h.fail_rate:.0%}</strong></p>'
        f"{table}</div>"
    )


class EmailAdapter(DistributionAdapter):
    """SMTP 邮件适配器。"""

    async def send(self, report: WeeklyReport, config: dict) -> bool:
        to_addrs = config.get("to_addrs", [])
        if not to_addrs:
            raise ValueError("收件人列表为空")

        html = _build_html(report)
        msg = MIMEText(html, "html", "utf-8")
        msg["Subject"] = f"拾讯周报 {report.year_week}（{report.date_range_start} ~ {report.date_range_end}）"
        msg["From"] = config.get("from_addr", config.get("smtp_user", ""))
        msg["To"] = ", ".join(to_addrs)

        use_tls = config.get("use_tls", True)
        smtp_host = config["smtp_host"]
        smtp_port = config["smtp_port"]
        smtp_user = config["smtp_user"]
        smtp_pass = config["smtp_pass"]

        loop = asyncio.get_running_loop()

        def _send():
            if use_tls:
                with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
                    server.login(smtp_user, smtp_pass)
                    server.sendmail(smtp_user, to_addrs, msg.as_string())
            else:
                with smtplib.SMTP(smtp_host, smtp_port) as server:
                    server.starttls()
                    server.login(smtp_user, smtp_pass)
                    server.sendmail(smtp_user, to_addrs, msg.as_string())

        try:
            await loop.run_in_executor(None, _send)
            logger.info("邮件周报发送成功: %s -> %s", smtp_user, to_addrs)
            return True
        except Exception as e:
            logger.error("邮件发送失败: %s", e)
            raise
