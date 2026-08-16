"""
Interactive tool to flag (or unflag) entries in your Project Vote history.
Flagged entries get a star and a highlight on the dashboard's Recent Votes
trail, so the ideas worth coming back to stand out from the rest.

Run this anytime from the root of your jdb-dashboard repo (same folder as
project_vote_log.json). It lists your recent picks, you type a number to
toggle its flag, and it saves. Type 'q' to quit.

After flagging, don't forget to commit and push so the flag shows up on
the live dashboard:
    git add project_vote_log.json
    git commit -m "Flag project ideas"
    git push
"""

import json
import pathlib

LOG_FILE = pathlib.Path("project_vote_log.json")


def load_log():
    if not LOG_FILE.exists():
        print("FAILED: project_vote_log.json not found in current directory.")
        print("Run this from the root of your jdb-dashboard repo.")
        return None
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"FAILED: could not read project_vote_log.json ({e}).")
        return None


def save_log(entries):
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)


def main():
    entries = load_log()
    if entries is None:
        return
    if not entries:
        print("No entries in project_vote_log.json yet -- nothing to flag.")
        return

    while True:
        print("\n" + "=" * 60)
        print("PROJECT VOTE HISTORY  (most recent first)")
        print("=" * 60)
        # Show newest first, but keep real list indices for toggling.
        display_order = list(enumerate(entries))[::-1]
        for idx, e in display_order:
            mark = "\u2605" if e.get("flagged") else " "
            tags = ", ".join(e.get("tags", []))
            print(f"[{idx:>2}] {mark}  {e['date']}  {e['title']}" + (f"  ({tags})" if tags else ""))

        choice = input("\nEnter a number to toggle its flag, or 'q' to quit: ").strip().lower()
        if choice == "q":
            break
        if not choice.isdigit() or int(choice) not in range(len(entries)):
            print("Not a valid entry number -- try again.")
            continue

        i = int(choice)
        entries[i]["flagged"] = not entries[i].get("flagged", False)
        save_log(entries)
        state = "FLAGGED" if entries[i]["flagged"] else "unflagged"
        print(f"SUCCESS: '{entries[i]['title']}' is now {state}.")

    print("\nDone. Remember to git add / commit / push project_vote_log.json")
    print("if you want the flags to show up on the live dashboard.")


if __name__ == "__main__":
    main()
