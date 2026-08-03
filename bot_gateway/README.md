# Bot Gateway (Telegram + Slack + WhatsApp)

## Telegram
- Webhook: `POST /api/bot/telegram/`
- Env: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`
- Setup: `python manage.py set_telegram_webhook https://<host>/api/bot/telegram/`

## Slack (Sequence 6)
- Webhook (Events + Slash + Interactivity): `POST /api/bot/slack/`
- Env: `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET`
- Guidance: `python manage.py slack_bot_setup`
- Scopes: `chat:write`, `commands`, `im:history`, `im:read`, `users:read`, `app_mentions:read`
- Slash: `/teamzen`, `/leaves`, `/checkin`, `/checkout`, `/payslip`, `/balance`
- Auth: same OTP email flow as Telegram (`BotSession.platform=slack`, `chat_id` = Slack user id)
- Check-in on Slack: reply with `lat,lng` after starting check-in (or use web/mobile)

## WhatsApp (Meta Cloud API)
- Webhook: `GET/POST /api/bot/whatsapp/`
- Env: `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_APP_SECRET`, `WHATSAPP_API_VERSION`
- Guidance: `python manage.py whatsapp_bot_setup`
- Meta console: developers.facebook.com → WhatsApp → Configuration
  - Callback URL: `https://<host>/api/bot/whatsapp/`
  - Verify token: same as `WHATSAPP_VERIFY_TOKEN`
  - Subscribe: `messages`
- Auth: OTP email (`BotSession.platform=whatsapp`, `chat_id` = phone digits)
- Check-in: attachment → Location → current location
- Sandbox: allowlist test recipient numbers in API Setup

All platforms share `BotService` and proactive `notify_bot_user`.
