"""Email templates for Assay.

Crafted with responsive, high-contrast, institutional styling matching
Assay's UI design (clean card layout, crisp typography, and brand accent).
"""

from __future__ import annotations

import html


def render_otp_email(otp_code: str, email: str) -> tuple[str, str]:
    """Render plain-text and responsive HTML email for 6-digit signup OTP verification.

    Returns:
        tuple[str, str]: (plain_text_content, html_content)
    """
    safe_email = html.escape(email)
    safe_otp = html.escape(otp_code.strip())

    text_body = f"""Assay - Email Verification

Your 6-digit verification code is: {safe_otp}

Enter this code on the registration page to verify your email address ({email}) and complete your account creation.

This code will expire in 10 minutes. If you did not request this verification code, you can safely ignore this email. No account will be created without your confirmation.

---
Assay · Automated equity research
https://assay.sahell.in
"""

    html_body = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="X-UA-Compatible" content="IE=edge">
  <title>Your Assay verification code</title>
  <!--[if mso]>
  <style type="text/css">
    body, table, td {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif !important; }}
  </style>
  <![endif]-->
</head>
<body style="margin: 0; padding: 0; background-color: #fafafa; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; color: #0a0a0a;">
  <!-- Preheader text for email preview snippets (clean, spam-safe) -->
  <div style="display: none; max-height: 0px; overflow: hidden; mso-hide: all;">
    {safe_otp} is your Assay verification code. Valid for 10 minutes.
  </div>

  <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #fafafa; padding: 32px 16px;">
    <tr>
      <td align="center">
        <!-- Main Card Container -->
        <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0" style="max-width: 480px; background-color: #ffffff; border: 1px solid #e4e4e7; border-radius: 12px; overflow: hidden; box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);">
          
          <!-- Header Bar with Assay Brand -->
          <tr>
            <td style="padding: 28px 32px 20px 32px; border-bottom: 1px solid #f4f4f5;">
              <table role="presentation" border="0" cellspacing="0" cellpadding="0">
                <tr>
                  <!-- Brand Tile -->
                  <td style="vertical-align: middle; width: 32px;">
                    <a href="https://assay.sahell.in" style="text-decoration: none; display: block;">
                      <div style="width: 30px; height: 30px; background-color: #0a0a0a; border-radius: 7px; text-align: center; line-height: 30px;">
                        <!-- Styled A mark with green accent line -->
                        <span style="color: #ffffff; font-weight: 700; font-size: 16px; letter-spacing: -0.05em; display: inline-block;">
                          A<span style="color: #22c55e; font-size: 18px; line-height: 0; margin-left: -2px;">&#8599;</span>
                        </span>
                      </div>
                    </a>
                  </td>
                  <td style="vertical-align: middle; padding-left: 10px;">
                    <a href="https://assay.sahell.in" style="font-size: 18px; font-weight: 700; color: #0a0a0a; letter-spacing: -0.03em; text-decoration: none;">Assay</a>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Main Content -->
          <tr>
            <td style="padding: 32px 32px 24px 32px;">
              <h1 style="margin: 0 0 10px 0; font-size: 22px; font-weight: 600; color: #0a0a0a; letter-spacing: -0.025em; line-height: 1.25;">
                Verify your email address
              </h1>
              <p style="margin: 0 0 24px 0; font-size: 14px; line-height: 1.6; color: #525252;">
                Use the verification code below to complete creating your account for <strong style="color: #0a0a0a; font-weight: 600;">{safe_email}</strong>.
              </p>

              <!-- OTP Code Box -->
              <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0" style="margin: 8px 0 24px 0;">
                <tr>
                  <td align="center" style="background-color: #fcfcfc; border: 1px solid #ebebeb; border-radius: 10px; padding: 22px 16px;">
                    <div style="font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.1em; color: #71717a; margin-bottom: 8px;">
                      Verification Code
                    </div>
                    <div style="font-family: ui-monospace, 'SF Mono', Menlo, Monaco, Consolas, 'Liberation Mono', monospace; font-size: 34px; font-weight: 700; letter-spacing: 10px; color: #0a0a0a; padding-left: 10px; line-height: 1.1;">
                      {safe_otp}
                    </div>
                    <div style="font-size: 12px; color: #71717a; margin-top: 10px; display: inline-block;">
                      Expires in <span style="font-weight: 600; color: #0a0a0a;">10 minutes</span>
                    </div>
                  </td>
                </tr>
              </table>

              <!-- Security Information -->
              <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0" style="border-top: 1px solid #f4f4f5; padding-top: 18px; margin-top: 4px;">
                <tr>
                  <td>
                    <p style="margin: 0 0 8px 0; font-size: 13px; line-height: 1.5; color: #71717a;">
                      If you didn't attempt to sign up for Assay, someone may have entered your address by accident. You can safely ignore this message &mdash; no account will be created.
                    </p>
                    <p style="margin: 0; font-size: 12px; line-height: 1.4; color: #a1a1a1;">
                      Never share this code with anyone. Assay will never ask for your code outside the registration screen.
                    </p>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Footer within card -->
          <tr>
            <td style="padding: 16px 32px; background-color: #fafafa; border-top: 1px solid #f4f4f5; text-align: center;">
              <span style="font-size: 12px; color: #71717a;">
                Assay &bull; <a href="https://assay.sahell.in" style="color: #71717a; text-decoration: none;">assay.sahell.in</a>
              </span>
            </td>
          </tr>

        </table>

        <!-- Outer Sub-footer -->
        <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0" style="max-width: 480px; margin-top: 16px;">
          <tr>
            <td align="center" style="font-size: 11px; color: #a1a1a1; line-height: 1.5;">
              This is an automated security verification email sent from <a href="https://assay.sahell.in" style="color: #71717a; text-decoration: underline;">Assay</a>.<br>
              &copy; Assay. All rights reserved.
            </td>
          </tr>
        </table>

      </td>
    </tr>
  </table>
</body>
</html>
"""
    return text_body, html_body


def render_password_reset_email(reset_link: str, email: str) -> tuple[str, str]:
    """Render plain-text and responsive HTML email for password reset.

    Returns:
        tuple[str, str]: (plain_text_content, html_content)
    """
    safe_email = html.escape(email)
    safe_link = html.escape(reset_link)

    text_body = f"""Assay - Password Reset

Someone asked to reset the password for your Assay account ({email}).

To choose a new password, open this link within the next hour:
{reset_link}

If you did not request this, you can safely ignore this email. Your password will stay the same until you use the link.

---
Assay · Automated equity research
https://assay.sahell.in
"""

    html_body = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="X-UA-Compatible" content="IE=edge">
  <title>Reset your Assay password</title>
  <!--[if mso]>
  <style type="text/css">
    body, table, td {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif !important; }}
  </style>
  <![endif]-->
</head>
<body style="margin: 0; padding: 0; background-color: #fafafa; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; color: #0a0a0a;">
  <!-- Preheader text for email preview snippets (clean, spam-safe) -->
  <div style="display: none; max-height: 0px; overflow: hidden; mso-hide: all;">
    Reset your Assay password. Link valid for 1 hour.
  </div>

  <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #fafafa; padding: 32px 16px;">
    <tr>
      <td align="center">
        <!-- Main Card Container -->
        <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0" style="max-width: 480px; background-color: #ffffff; border: 1px solid #e4e4e7; border-radius: 12px; overflow: hidden; box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);">
          
          <!-- Header Bar with Assay Brand -->
          <tr>
            <td style="padding: 28px 32px 20px 32px; border-bottom: 1px solid #f4f4f5;">
              <table role="presentation" border="0" cellspacing="0" cellpadding="0">
                <tr>
                  <!-- Brand Tile -->
                  <td style="vertical-align: middle; width: 32px;">
                    <a href="https://assay.sahell.in" style="text-decoration: none; display: block;">
                      <div style="width: 30px; height: 30px; background-color: #0a0a0a; border-radius: 7px; text-align: center; line-height: 30px;">
                        <span style="color: #ffffff; font-weight: 700; font-size: 16px; letter-spacing: -0.05em; display: inline-block;">
                          A<span style="color: #22c55e; font-size: 18px; line-height: 0; margin-left: -2px;">&#8599;</span>
                        </span>
                      </div>
                    </a>
                  </td>
                  <td style="vertical-align: middle; padding-left: 10px;">
                    <a href="https://assay.sahell.in" style="font-size: 18px; font-weight: 700; color: #0a0a0a; letter-spacing: -0.03em; text-decoration: none;">Assay</a>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Main Content -->
          <tr>
            <td style="padding: 32px 32px 24px 32px;">
              <h1 style="margin: 0 0 10px 0; font-size: 22px; font-weight: 600; color: #0a0a0a; letter-spacing: -0.025em; line-height: 1.25;">
                Reset your password
              </h1>
              <p style="margin: 0 0 24px 0; font-size: 14px; line-height: 1.6; color: #525252;">
                We received a request to reset the password for <strong style="color: #0a0a0a; font-weight: 600;">{safe_email}</strong>. Click the button below to set a new password:
              </p>

              <!-- Action Button -->
              <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0" style="margin: 8px 0 24px 0;">
                <tr>
                  <td align="center">
                    <a href="{safe_link}" style="display: inline-block; background-color: #0a0a0a; color: #ffffff; font-size: 14px; font-weight: 600; text-decoration: none; padding: 12px 28px; border-radius: 8px;">
                      Reset Password
                    </a>
                  </td>
                </tr>
              </table>

              <!-- Security Information -->
              <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0" style="border-top: 1px solid #f4f4f5; padding-top: 18px; margin-top: 4px;">
                <tr>
                  <td>
                    <p style="margin: 0 0 8px 0; font-size: 13px; line-height: 1.5; color: #71717a;">
                      This link will expire in 1 hour. If you didn't request a password reset, you can safely ignore this email &mdash; your password remains unchanged.
                    </p>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Footer within card -->
          <tr>
            <td style="padding: 16px 32px; background-color: #fafafa; border-top: 1px solid #f4f4f5; text-align: center;">
              <span style="font-size: 12px; color: #71717a;">
                Assay &bull; <a href="https://assay.sahell.in" style="color: #71717a; text-decoration: none;">assay.sahell.in</a>
              </span>
            </td>
          </tr>

        </table>

        <!-- Outer Sub-footer -->
        <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0" style="max-width: 480px; margin-top: 16px;">
          <tr>
            <td align="center" style="font-size: 11px; color: #a1a1a1; line-height: 1.5;">
              This is an automated operational email sent from <a href="https://assay.sahell.in" style="color: #71717a; text-decoration: underline;">Assay</a>.<br>
              &copy; Assay. All rights reserved.
            </td>
          </tr>
        </table>

      </td>
    </tr>
  </table>
</body>
</html>
"""
    return text_body, html_body


def render_password_reset_otp_email(otp_code: str, email: str) -> tuple[str, str]:
    """Render plain-text and responsive HTML email for 6-digit password reset OTP verification.

    Returns:
        tuple[str, str]: (plain_text_content, html_content)
    """
    safe_email = html.escape(email)
    safe_otp = html.escape(otp_code.strip())

    text_body = f"""Assay - Password Reset Code

Your 6-digit verification code is: {safe_otp}

Enter this code on the password reset page to reset the password for your Assay account ({email}).

This code will expire in 10 minutes. If you did not request this verification code, you can safely ignore this email. Your password will stay the same.

---
Assay · Automated equity research
https://assay.sahell.in
"""

    html_body = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="X-UA-Compatible" content="IE=edge">
  <title>Your Assay password reset code</title>
  <!--[if mso]>
  <style type="text/css">
    body, table, td {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif !important; }}
  </style>
  <![endif]-->
</head>
<body style="margin: 0; padding: 0; background-color: #fafafa; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; color: #0a0a0a;">
  <!-- Preheader text for email preview snippets -->
  <div style="display: none; max-height: 0px; overflow: hidden; mso-hide: all;">
    {safe_otp} is your Assay password reset code. Valid for 10 minutes.
  </div>

  <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #fafafa; padding: 32px 16px;">
    <tr>
      <td align="center">
        <!-- Main Card Container -->
        <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0" style="max-width: 480px; background-color: #ffffff; border: 1px solid #e4e4e7; border-radius: 12px; overflow: hidden; box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);">
          
          <!-- Header Bar with Assay Brand -->
          <tr>
            <td style="padding: 28px 32px 20px 32px; border-bottom: 1px solid #f4f4f5;">
              <table role="presentation" border="0" cellspacing="0" cellpadding="0">
                <tr>
                  <!-- Brand Tile -->
                  <td style="vertical-align: middle; width: 32px;">
                    <a href="https://assay.sahell.in" style="text-decoration: none; display: block;">
                      <div style="width: 30px; height: 30px; background-color: #0a0a0a; border-radius: 7px; text-align: center; line-height: 30px;">
                        <span style="color: #ffffff; font-weight: 700; font-size: 16px; letter-spacing: -0.05em; display: inline-block;">
                          A<span style="color: #22c55e; font-size: 18px; line-height: 0; margin-left: -2px;">&#8599;</span>
                        </span>
                      </div>
                    </a>
                  </td>
                  <td style="vertical-align: middle; padding-left: 10px;">
                    <a href="https://assay.sahell.in" style="font-size: 18px; font-weight: 700; color: #0a0a0a; letter-spacing: -0.03em; text-decoration: none;">Assay</a>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Main Content -->
          <tr>
            <td style="padding: 32px 32px 24px 32px;">
              <h1 style="margin: 0 0 10px 0; font-size: 22px; font-weight: 600; color: #0a0a0a; letter-spacing: -0.025em; line-height: 1.25;">
                Reset your password
              </h1>
              <p style="margin: 0 0 24px 0; font-size: 14px; line-height: 1.6; color: #525252;">
                We received a request to reset the password for <strong style="color: #0a0a0a; font-weight: 600;">{safe_email}</strong>. Use the verification code below to proceed:
              </p>

              <!-- OTP Code Box -->
              <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0" style="margin: 8px 0 24px 0;">
                <tr>
                  <td align="center" style="background-color: #fcfcfc; border: 1px solid #ebebeb; border-radius: 10px; padding: 22px 16px;">
                    <div style="font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.1em; color: #71717a; margin-bottom: 8px;">
                      Password Reset Code
                    </div>
                    <div style="font-family: ui-monospace, 'SF Mono', Menlo, Monaco, Consolas, 'Liberation Mono', monospace; font-size: 34px; font-weight: 700; letter-spacing: 10px; color: #0a0a0a; padding-left: 10px; line-height: 1.1;">
                      {safe_otp}
                    </div>
                    <div style="font-size: 12px; color: #71717a; margin-top: 10px; display: inline-block;">
                      Expires in <span style="font-weight: 600; color: #0a0a0a;">10 minutes</span>
                    </div>
                  </td>
                </tr>
              </table>

              <!-- Security Information -->
              <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0" style="border-top: 1px solid #f4f4f5; padding-top: 18px; margin-top: 4px;">
                <tr>
                  <td>
                    <p style="margin: 0 0 8px 0; font-size: 13px; line-height: 1.5; color: #71717a;">
                      If you did not request a password reset, you can safely ignore this email &mdash; your account and password remain secure.
                    </p>
                    <p style="margin: 0; font-size: 12px; line-height: 1.4; color: #a1a1a1;">
                      Never share this code with anyone. Assay support will never ask for your code.
                    </p>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Footer within card -->
          <tr>
            <td style="padding: 16px 32px; background-color: #fafafa; border-top: 1px solid #f4f4f5; text-align: center;">
              <span style="font-size: 12px; color: #71717a;">
                Assay &bull; <a href="https://assay.sahell.in" style="color: #71717a; text-decoration: none;">assay.sahell.in</a>
              </span>
            </td>
          </tr>

        </table>

        <!-- Outer Sub-footer -->
        <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0" style="max-width: 480px; margin-top: 16px;">
          <tr>
            <td align="center" style="font-size: 11px; color: #a1a1a1; line-height: 1.5;">
              This is an automated security verification email sent from <a href="https://assay.sahell.in" style="color: #71717a; text-decoration: underline;">Assay</a>.<br>
              &copy; Assay. All rights reserved.
            </td>
          </tr>
        </table>

      </td>
    </tr>
  </table>
</body>
</html>
"""
    return text_body, html_body
