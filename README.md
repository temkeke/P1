# P1 Telegram Dialer Bot

This project provides a Telegram bot that coordinates automated outbound
calling through a SIP trunk. The bot is designed around the `aiovoip`
client and manages lead uploads, job tracking, preset audio selection,
and admin controlled whitelisting.

## Getting started

1. Create a Python environment and install the requirements:
   ```bash
   pip install -r requirements.txt
   ```
2. Export the required configuration variables (or edit `config.py`):
   ```bash
   export P1_BOT_TOKEN=your_bot_token
   export P1_ADMIN_IDS=123456789
   export P1_SIP_HOST=sip.example.com
   export P1_SIP_USERNAME=username
   export P1_SIP_PASSWORD=password
   ```
3. Add `intro.wav` and `outro.wav` audio files for each preset under the
   `presets/` directory.
4. Start the bot:
   ```bash
   python bot.py
   ```

## Presets

Each preset directory must contain an `intro.wav` and `outro.wav` file.
The intro clip plays when the call is answered and the outro clip is
played once the callee presses `1`.

## Development notes

A lightweight `aiovoip` stub is included for local development. Replace
it with the real library in production to connect to your SIP provider.
