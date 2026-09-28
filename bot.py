import os
import json
import requests
from datetime import datetime, timezone, timedelta

ODDS_API_KEY = os.environ["ODDS_API_KEY"]
TG_BOT_TOKEN = os.environ["TG_BOT_TOKEN"]
TG_CHAT_ID = "224023328"

THRESHOLD = 3.00

# Soccer leagues returned by The Odds API.
# The scanner checks every soccer sport key returned by /v4/sports.
API_BASE = "https://api.the-odds-api.com/v4"

STATE_FILE = "sent_alerts.json"


def load_sent_alerts():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_sent_alerts(alerts):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(list(alerts), f)


def get_soccer_sports():
    url = f"{API_BASE}/sports/"
    params = {
        "apiKey": ODDS_API_KEY,
        "all": "true"
    }

    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()

    sports = response.json()

    return [
        sport["key"]
        for sport in sports
        if sport.get("group", "").lower() == "soccer"
    ]


def get_odds(sport_key):
    url = f"{API_BASE}/sports/{sport_key}/odds/"

    params = {
        "apiKey": ODDS_API_KEY,
        "regions": "eu",
        "markets": "h2h",
        "oddsFormat": "decimal"
    }

    response = requests.get(url, params=params, timeout=30)

    if response.status_code != 200:
        print(f"Error for {sport_key}: {response.status_code}")
        return []

    return response.json()


def send_telegram(message):
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"

    data = {
        "chat_id": TG_CHAT_ID,
        "text": message
    }

    response = requests.post(url, data=data, timeout=30)
    response.raise_for_status()


def scan_match(match):
    home = match.get("home_team", "Home")
    away = match.get("away_team", "Away")

    best_home = None
    best_draw = None
    best_away = None

    home_bookmaker = ""
    draw_bookmaker = ""
    away_bookmaker = ""

    # Find the highest 1, X and 2 odds across bookmakers.
    for bookmaker in match.get("bookmakers", []):
        bookmaker_name = bookmaker.get("title", "Unknown")

        for market in bookmaker.get("markets", []):
            if market.get("key") != "h2h":
                continue

            for outcome in market.get("outcomes", []):
                name = outcome.get("name")
                price = outcome.get("price")

                if not isinstance(price, (int, float)):
                    continue

                if name == home:
                    if best_home is None or price > best_home:
                        best_home = price
                        home_bookmaker = bookmaker_name

                elif name == away:
                    if best_away is None or price > best_away:
                        best_away = price
                        away_bookmaker = bookmaker_name

                elif name == "Draw":
                    if best_draw is None or price > best_draw:
                        best_draw = price
                        draw_bookmaker = bookmaker_name

    # We need all three 1/X/2 odds.
    if best_home is None or best_draw is None or best_away is None:
        return None

    # IMPORTANT:
    # Red signal = all three odds strictly greater than 3.00.
    if (
        best_home > THRESHOLD
        and best_draw > THRESHOLD
        and best_away > THRESHOLD
    ):
        return {
            "home": home,
            "away": away,
            "one": best_home,
            "draw": best_draw,
            "two": best_away,
            "book_home": home_bookmaker,
            "book_draw": draw_bookmaker,
            "book_away": away_bookmaker,
            "commence": match.get("commence_time", "")
        }

    return None


def main():
    print("Starting football odds scanner...")

    sent_alerts = load_sent_alerts()

    sports = get_soccer_sports()

    print(f"Soccer competitions found: {len(sports)}")

    for sport_key in sports:
        print(f"Scanning: {sport_key}")

        matches = get_odds(sport_key)

        for match in matches:
            signal = scan_match(match)

            if not signal:
                continue

            match_id = match.get("id")

            if not match_id:
                match_id = (
                    f"{signal['home']}-"
                    f"{signal['away']}-"
                    f"{signal['commence']}"
                )

            if match_id in sent_alerts:
                continue

            message = (
                "🚨 3 KÒT > 3.00 🚨\n\n"
                f"⚽ {signal['home']} vs {signal['away']}\n\n"
                f"1️⃣ {signal['one']:.2f} "
                f"({signal['book_home']})\n"
                f"❌ X {signal['draw']:.2f} "
                f"({signal['book_draw']})\n"
                f"2️⃣ {signal['two']:.2f} "
                f"({signal['book_away']})\n\n"
                "🔴 1 > 3.00\n"
                "🔴 X > 3.00\n"
                "🔴 2 > 3.00"
            )

            try:
                send_telegram(message)
                print("Telegram alert sent.")

                sent_alerts.add(match_id)
                save_sent_alerts(sent_alerts)

            except Exception as e:
                print(f"Telegram error: {e}")


if __name__ == "__main__":
    main()
