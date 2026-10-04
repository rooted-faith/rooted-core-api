"""
Locale-aware OTP email content (subject, plain text, HTML). No links, remote images, or tracking.
"""

from dataclasses import dataclass
from html import escape
from typing import Optional

_TRADITIONAL_CHINESE = "zh-TW"


@dataclass(frozen=True)
class OtpEmailContent:
    subject: str
    text: str
    html: str


def render_otp_email(code: str, *, locale: Optional[str], expire_minutes: int) -> OtpEmailContent:
    """Traditional Chinese for zh-TW; every other locale falls back to English."""
    if locale == _TRADITIONAL_CHINESE:
        lang, subject = "zh-Hant", f"你的 Rooted 驗證碼：{code}"
        intro = "請輸入以下驗證碼以登入 Rooted："
        validity = f"此驗證碼將在 {expire_minutes} 分鐘後失效，且只能使用一次。"
        ignore = "如果這不是你本人的操作，請直接忽略這封郵件。"
    else:
        lang, subject = "en", f"Your Rooted verification code: {code}"
        intro = "Enter this code to sign in to Rooted:"
        validity = f"This code expires in {expire_minutes} minutes and can be used only once."
        ignore = "If you didn't request this, you can safely ignore this email."

    text = f"{intro}\n\n{code}\n\n{validity}\n{ignore}\n"
    html = (
        f'<!DOCTYPE html><html lang="{lang}"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{escape(subject)}</title></head>"
        '<body style="margin:0;padding:24px;background:#f6f6f4;color:#1f2937;'
        "font-family:-apple-system,'Segoe UI',Helvetica,Arial,sans-serif;\">"
        '<div style="max-width:480px;margin:0 auto;background:#ffffff;padding:32px;border-radius:12px;">'
        f'<p style="font-size:16px;line-height:1.5;margin:0 0 16px;">{escape(intro)}</p>'
        f'<p style="font-size:36px;font-weight:700;letter-spacing:8px;margin:0 0 24px;color:#111827;">{escape(code)}</p>'
        f'<p style="font-size:14px;line-height:1.5;margin:0 0 8px;color:#374151;">{escape(validity)}</p>'
        f'<p style="font-size:14px;line-height:1.5;margin:0;color:#374151;">{escape(ignore)}</p>'
        "</div></body></html>"
    )
    return OtpEmailContent(subject=subject, text=text, html=html)
