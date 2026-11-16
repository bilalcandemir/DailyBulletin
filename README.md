# The [Name]'s Times

A personal morning newspaper that prints itself every day at 07:00. Three-column layout inspired by the New York Times — with your tasks, habits, schedule, and the day's news.

![bulletin preview](https://raw.githubusercontent.com/bilalcandemir/DailyBulletin/main/preview.png)

## What's Inside

- **Office Tasks** — today's to-do list, with Jira deadlines surfaced automatically
- **Sports & Habits** — weekly habit tracker (walking, reading, meditation, etc.)
- **Today's Schedule** — day-specific routine and sport activity
- **World News** — headlines from the Guardian API (world, technology, politics)
- **Weather** — current conditions via OpenWeatherMap
- **Notes** — write notes during the day, they appear as tasks the next morning

## Requirements

- Python 3.9+
- macOS or Linux (cron job)
- A black-and-white laser printer (recommended: Brother HL-L2350DW)

## Setup

**1. Clone the repo**
```bash
git clone https://github.com/bilalcandemir/DailyBulletin
cd DailyBulletin
```

**2. Install dependencies**
```bash
pip3 install pyyaml jinja2 requests playwright
python3 -m playwright install chromium
```

**3. Configure**
```bash
cp config.example.yaml config.yaml
cp tasks.example.yaml tasks.yaml
```
Open `config.yaml` and fill in:
- Your city name
- [Guardian API key](https://open-platform.theguardian.com/access/support-sandbox) (free)
- [OpenWeatherMap API key](https://openweathermap.org/api) (free)

**4. Personalize**

In `templates/bulletin.html`, replace `The Bilal's Times` with your own name.

**5. Test**
```bash
python3 generate.py
```
The PDF opens in `output/`.

**6. Automate (cron job — every morning at 07:00)**
```bash
crontab -e
```
Add:
```
0 7 * * * cd /path/to/DailyBulletin && /usr/local/bin/python3 generate.py >> /path/to/DailyBulletin/cron.log 2>&1
```

## Jira Integration

Get a [personal access token](https://id.atlassian.com/manage-profile/security/api-tokens) from Atlassian and save it:
```bash
echo "YOUR_TOKEN" > ~/.bulletin_jira_token
chmod 600 ~/.bulletin_jira_token
```
Then set `jira.enabled: true` in `config.yaml` and fill in `cloud_id` and `email`.

Issues due within 1 day will appear automatically in the left column.

## Notes System

Add a shell function to your `~/.zshrc`:
```bash
note() { echo "$1" >> ~/DailyBulletin/notes.txt && echo "✓ Note added: $1"; }
```
Then during the day:
```bash
note "Prepare sprint demo slides"
```
Tomorrow morning those show up in the bulletin as tasks.

## Printer Setup

When your printer is connected, find its name:
```bash
lpstat -p
```
Add it to `config.yaml`:
```yaml
printer:
  enabled: true
  printer_name: "Brother_HL_L2350DW"
  bw_mode: true
```

> **Warning:** Never leave `printer_name` empty with `enabled: true`. macOS will send it to your default printer — which might be the office printer. I sent 50+ test prints to my colleagues before I figured this out.

## Customization

- **Habits** — edit the `habits` list in `config.yaml`
- **Weekly schedule** — edit `weekly_schedule.yaml`
- **News sections** — change `sections` in `config.yaml` (world, technology, business, science, sport, culture, politics)
- **Quotes** — add your own to `quotes.txt`

## License

MIT
